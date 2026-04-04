"""
Agent Graph with LangGraph Workflow

This module creates the LangGraph workflow where:
- The selected LLM (OpenAI/Gemini/Ollama) acts as the intelligent agent
- It decides when to use tools to retrieve information
- Local file tools provide university-specific information
- The same LLM generates the final user-facing responses
- Multi-hop reasoning performs parallel retrieval across domains and
  aggregates results before the LLM composes its answer
"""

from typing import Annotated, Sequence, TypedDict, Optional, Literal
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.messages import BaseMessage, SystemMessage, AIMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.postgres import PostgresSaver

from app.llm_provider import get_current_llm, llm_provider
from app.tools import available_tools
from app.config import DATABASE_URL_SYNC
from app.query_router import (
    classify_query,
    get_routing_context,
    get_domain_tools_for_query,
    Domain,
)
from app.vector_store import search_documents
from app.golden_examples import get_relevant_golden_examples, format_golden_examples_for_prompt


# ── Multi-hop result aggregation ──────────────────────────────────────

_DOMAIN_TO_CATEGORY: dict[Domain, str] = {
    Domain.ACADEMIC: "Academic",
    Domain.ADMINISTRATIVE: "Administrative",
    Domain.EDUCATIONAL: "Educational",
}


def _aggregate_multi_hop_results(
    results_by_domain: dict[Domain, list[dict]],
) -> str:
    """
    Merge parallel-retrieval results from multiple domains into a single
    context block that can be injected into the LLM system prompt.

    Results are grouped by domain, deduplicated by (filename, chunk_index),
    and sorted within each group by descending relevance score.
    """
    seen: set[tuple[str, int]] = set()
    sections: list[str] = []

    for domain, hits in results_by_domain.items():
        if not hits:
            continue
        # Sort best-first within each domain
        sorted_hits = sorted(hits, key=lambda h: h["score"], reverse=True)
        domain_lines: list[str] = []
        for h in sorted_hits:
            key = (h["filename"], h.get("chunk_index", 0))
            if key in seen:
                continue
            seen.add(key)
            source = (
                f"[SOURCE: {h['filename']} | {h['category']} | relevance: {h['score']}]"
            )
            domain_lines.append(f"{source}\n{h['text']}")
        if domain_lines:
            header = f"=== {domain.value.upper()} DOMAIN ==="
            sections.append(header + "\n" + "\n---\n".join(domain_lines))

    if not sections:
        return ""

    return (
        "[Multi-Hop Retrieval — Aggregated Cross-Domain Context]\n\n"
        + "\n\n".join(sections)
    )


# ── Agent State ───────────────────────────────────────────────────────

class AgentState(TypedDict):
    """State maintained throughout the conversation."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    multi_hop_context: str  # Pre-retrieved cross-domain context (empty if N/A)


def multi_hop_retrieval_node(state: AgentState) -> AgentState:
    """
    Multi-Hop Retrieval Node — Parallel Cross-Domain Search (Paper §4.3)

    For multi-domain queries this node runs **before** the agent LLM.
    It performs parallel semantic search across every matched domain
    using ``concurrent.futures`` and aggregates the results into a
    single context block stored in ``state["multi_hop_context"]``.

    Single-domain queries pass through without modification so the
    normal tool-calling flow handles them.
    """
    print("---NODE: MULTI-HOP RETRIEVAL CHECK---")

    # Extract the latest user message
    user_messages = [
        m for m in state["messages"]
        if hasattr(m, "type") and m.type == "human"
    ]
    if not user_messages:
        return {"multi_hop_context": ""}

    latest_query = (
        user_messages[-1].content
        if hasattr(user_messages[-1], "content")
        else str(user_messages[-1])
    )

    routing_result = classify_query(latest_query)

    if not routing_result.is_multi_domain:
        print("Single-domain query — skipping parallel retrieval")
        return {"multi_hop_context": ""}

    matched_domains = routing_result.domains
    print(
        f"Multi-domain query detected — launching parallel retrieval "
        f"across {[d.value for d in matched_domains]}"
    )

    # ── Parallel retrieval across matched domains ──────────────
    results_by_domain: dict[Domain, list[dict]] = {}

    with ThreadPoolExecutor(max_workers=len(matched_domains)) as pool:
        future_to_domain = {
            pool.submit(
                search_documents, latest_query, _DOMAIN_TO_CATEGORY[d]
            ): d
            for d in matched_domains
        }
        for future in as_completed(future_to_domain):
            domain = future_to_domain[future]
            try:
                results_by_domain[domain] = future.result()
                print(
                    f"  ✓ {domain.value}: {len(results_by_domain[domain])} hits"
                )
            except Exception as exc:
                print(f"  ✗ {domain.value} retrieval failed: {exc}")
                results_by_domain[domain] = []

    aggregated = _aggregate_multi_hop_results(results_by_domain)

    if aggregated:
        total_hits = sum(len(v) for v in results_by_domain.values())
        print(
            f"Multi-hop aggregation complete — {total_hits} total chunks "
            f"from {len(results_by_domain)} domains"
        )
    else:
        print("No relevant results from parallel retrieval")

    return {"multi_hop_context": aggregated}


def agent_node(state: AgentState) -> AgentState:
    """
    Agent Node - Uses the selected LLM with domain-aware tool routing
    
    The LLM analyzes the user's question and decides:
    1. Whether to use tools to retrieve information from local files
    2. Which tools to call and with what parameters
    3. How to generate the response
    
    Domain-aware routing classifies the query and dynamically binds
    only the relevant domain tools, improving accuracy and reducing
    unnecessary tool calls.

    If ``multi_hop_context`` is present in the state (set by the
    multi-hop retrieval node), it is injected into the system prompt
    so the LLM can synthesize a cross-domain answer without needing
    to make additional tool calls.
    """
    print("---NODE: AGENT LLM---")
    
    # Get the current LLM
    llm = get_current_llm(temperature=0.3)
    
    # Extract the latest user message for domain classification
    user_messages = [m for m in state["messages"] if hasattr(m, 'type') and m.type == 'human']
    latest_query = ""
    if user_messages:
        latest_query = user_messages[-1].content if hasattr(user_messages[-1], 'content') else str(user_messages[-1])
    elif state["messages"]:
        # Fallback: try the last message tuple format
        last = state["messages"][-1]
        if isinstance(last, tuple) and len(last) == 2:
            latest_query = last[1]
        elif hasattr(last, 'content'):
            latest_query = last.content
    
    # ── Multi-hop pre-retrieved context ────────────────────────
    multi_hop_ctx = state.get("multi_hop_context", "") or ""
    multi_hop_prompt_block = ""
    if multi_hop_ctx:
        print("Injecting multi-hop aggregated context into system prompt")
        multi_hop_prompt_block = (
            "\n\n--- PRE-RETRIEVED CROSS-DOMAIN CONTEXT (Multi-Hop) ---\n"
            f"{multi_hop_ctx}\n"
            "--- END CROSS-DOMAIN CONTEXT ---\n\n"
            "The above context was retrieved in parallel from multiple knowledge-base "
            "domains. Use it to compose a comprehensive answer. You may still call "
            "tools if you need additional details, but prefer the pre-retrieved "
            "context when it already answers the question.\n"
        )

    # ── Golden examples context (best-effort) ───────────────────
    golden_prompt_block = ""
    if latest_query:
        golden_examples = get_relevant_golden_examples(latest_query, limit=3)
        if golden_examples:
            print(f"Injecting {len(golden_examples)} golden example(s) into prompt")
            golden_prompt_block = "\n\n" + format_golden_examples_for_prompt(golden_examples) + "\n"

    # Check if model supports tools
    if llm_provider.supports_tools():
        print("Using LLM with tool support")
        
        # Domain-aware routing: classify query and select relevant tools
        domain_tools = get_domain_tools_for_query(latest_query)
        routing_context = get_routing_context(latest_query)
        routing_result = classify_query(latest_query)
        
        print(f"Domain routing: {[d.value for d in routing_result.domains]} "
              f"(scores: {routing_result.scores})")
        print(f"Binding {len(domain_tools)} tool(s): "
              f"{[t.name for t in domain_tools]}")
        
        llm_with_tools = llm.bind_tools(domain_tools)
        
        system_message = SystemMessage(content=f"""You are a helpful university chatbot assistant with access to local university information files.

{routing_context}
{multi_hop_prompt_block}
    {golden_prompt_block}
HOW TO RESPOND:
1. For ANY question, ALWAYS use the appropriate tool first to search the university knowledge base
2. If the tools return relevant information, answer BASED ON that information and CITE THE SOURCE (see citation rules below)
3. If the tools return "The related data is not present" or no relevant information is found, you MAY still answer the question using your general knowledge, BUT you MUST clearly add a disclaimer like:
   "⚠️ *Note: This answer is based on general knowledge and was not retrieved from the university knowledge base.*"
4. For multi-domain questions, synthesize information from ALL relevant domains into a single coherent answer
5. **Be concise and direct.** Answer the specific question the user asked without unnecessary elaboration or filler. Get to the point quickly.
6. Use bullet points or numbered lists for multiple items instead of long paragraphs.
7. Do NOT repeat the question back. Do NOT add lengthy introductions or conclusions.
8. Keep responses focused — typically 3-8 sentences unless the question genuinely requires a detailed answer.

--- CITATION RULES (MANDATORY) ---
Tool results contain lines like `[SOURCE: filename | category | relevance: score]`.
You MUST follow these citation rules when knowledge-base results are used:

1. **Inline citations**: When using information from a source, cite it naturally in your answer.
   Example: "According to *university_info.txt*, the tuition fee for B.Tech is ₹1,20,000 per year."
2. **Sources section**: At the END of your response, add a horizontal rule followed by a markdown
   sources list using this EXACT format:

   ---
   **Sources:**
   - 📄 `filename.txt` (Category)
   - 📄 `another_file.txt` (Category)

   List ONLY the files you actually referenced. Do NOT list files that were returned but not used.
3. If the answer is based entirely on general knowledge (no tool results used), do NOT add a Sources section.
4. Never expose raw relevance scores to the user.
--- END CITATION RULES ---

Your knowledge base is organized in categories:
1. Academic: Calendars, schedules, dates, holidays
2. Administrative: Policies, procedures, contact info, fees, financial aid, scholarships, refunds
3. Educational: Course materials and resources

Available tools (USE THESE FIRST):
- search_university_info: For policies, procedures, programs, fees, financial aid, services (Administrative)
- search_academic_calendar: For dates, holidays, deadlines, events (Academic)
- check_if_date_is_holiday: To verify if a specific date is a holiday
- get_university_contact_info: For department contact information
- search_educational_resources: For course materials and educational content
- search_all_domains: For queries spanning multiple topics or unclear domain

Tool selection guide:
- Questions about tuition, payments, fees, scholarships, refunds → use search_university_info
- Questions about dates, holidays, deadlines → use search_academic_calendar or check_if_date_is_holiday
- Questions about contact info → use get_university_contact_info
- Questions about courses, materials, programming, subjects → use search_educational_resources
- General questions → use search_educational_resources first, then answer with general knowledge if not found
- Multi-domain questions (e.g. "refund policy if I drop a course") → use tools from ALL relevant domains

IMPORTANT: Always search the knowledge base first. Only fall back to general knowledge if the tools find nothing. Always be transparent about the source of your answer.""")
        
        messages = [system_message] + list(state["messages"])
        response = llm_with_tools.invoke(messages)
    else:
        print("Using LLM WITHOUT tool support - direct responses only")
        
        system_message = SystemMessage(content="""You are a helpful university chatbot assistant.

Provide clear, concise, and helpful responses to user questions. Be direct — answer the specific question without unnecessary elaboration. Use bullet points for lists. Keep responses focused, typically 3-8 sentences unless the question genuinely requires more detail.

Answer to the best of your knowledge about university-related topics including:
- Academic programs and courses
- Tuition and fees
- Academic calendars and deadlines
- University policies and procedures
- General educational topics

Be friendly, informative, and professional. If you don't know something specific to this university, say so honestly.""")

        if golden_prompt_block:
            system_message = SystemMessage(content=system_message.content + "\n\n" + golden_prompt_block)
        
        messages = [system_message] + list(state["messages"])
        response = llm.invoke(messages)
    
    return {"messages": [response]}


def should_continue(state: AgentState) -> Literal["tools", "end"]:
    """Decide whether to call tools or end."""
    print("---DECISION: SHOULD CONTINUE?---")
    
    last_message = state["messages"][-1]
    
    # Check if model supports tools first
    if not llm_provider.supports_tools():
        print("NO: Model doesn't support tools, ending")
        return "end"
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        print(f"YES: Calling {len(last_message.tool_calls)} tool(s)")
        return "tools"
    else:
        print("NO: Ending")
        return "end"


# Create tool node for executing tools
tool_node = ToolNode(available_tools)


def create_agent_graph():
    """
    Creates and compiles the agent graph.
    
    Flow:
    1. User question → Agent LLM (decides if tools needed)
    2. If tools needed → Execute tools → Back to Agent
    3. Agent generates response → End
    """
    print("---CREATING AGENT GRAPH---")
    
    # Initialize PostgreSQL checkpointer for persistent conversation memory
    try:
        checkpointer = PostgresSaver.from_conn_string(DATABASE_URL_SYNC)
        checkpointer.setup()  # Creates checkpoint tables if they don't exist
        print("PostgreSQL checkpointer initialized - conversation history will persist across restarts")
    except Exception as e:
        print(f"Warning: Could not initialize PostgreSQL checkpointer: {e}")
        print("Falling back to no checkpointer - conversation history will not persist")
        checkpointer = None
    
    # Build the graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("multi_hop_retrieval", multi_hop_retrieval_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    
    # Entry → multi-hop parallel retrieval (runs once per user turn)
    workflow.set_entry_point("multi_hop_retrieval")
    
    # Multi-hop retrieval always flows into the agent
    workflow.add_edge("multi_hop_retrieval", "agent")
    
    # Add conditional edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END,
        }
    )
    
    # Tools loop back to agent for processing results
    workflow.add_edge("tools", "agent")
    
    # Compile with checkpointer
    app = workflow.compile(checkpointer=checkpointer)
    
    print("Agent graph compiled successfully")
    return app


# For testing
if __name__ == "__main__":
    app = create_agent_graph()
    
    test_questions = [
        "How can I pay my tuition fees?",
        "What is SQL and do we use it at the university?",
        "Is November 1 a holiday?",
    ]
    
    thread_config = {"configurable": {"thread_id": "test-session"}}
    
    for question in test_questions:
        print(f"\n{'='*60}")
        print(f"QUESTION: {question}")
        print('='*60)
        
        result = app.invoke(
            {"messages": [("user", question)]},
            config=thread_config
        )
        
        final_message = result["messages"][-1]
        print(f"\nANSWER: {final_message.content}")
        print('='*60)
