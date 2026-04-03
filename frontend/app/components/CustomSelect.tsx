'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import styles from './CustomSelect.module.css';

interface Option {
  value: string;
  label: string;
}

interface CustomSelectProps {
  options: Option[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  id?: string;
  className?: string;
}

export default function CustomSelect({
  options,
  value,
  onChange,
  placeholder = 'Select an option',
  disabled = false,
  id,
  className = '',
}: CustomSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const selectedOption = options.find((opt) => opt.value === value);

  // Close on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Focus management
  useEffect(() => {
    if (isOpen && focusedIndex >= 0 && listRef.current) {
      const options = listRef.current.querySelectorAll('[role="option"]');
      (options[focusedIndex] as HTMLElement)?.focus();
    }
  }, [isOpen, focusedIndex]);

  const handleToggle = () => {
    if (!disabled) {
      setIsOpen(!isOpen);
      if (!isOpen) {
        const selectedIdx = options.findIndex((opt) => opt.value === value);
        setFocusedIndex(selectedIdx >= 0 ? selectedIdx : 0);
      }
    }
  };

  const handleSelect = useCallback(
    (optionValue: string) => {
      onChange(optionValue);
      setIsOpen(false);
      triggerRef.current?.focus();
    },
    [onChange]
  );

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (disabled) return;

      switch (event.key) {
        case 'Enter':
        case ' ':
          event.preventDefault();
          if (!isOpen) {
            setIsOpen(true);
            const selectedIdx = options.findIndex((opt) => opt.value === value);
            setFocusedIndex(selectedIdx >= 0 ? selectedIdx : 0);
          } else if (focusedIndex >= 0) {
            handleSelect(options[focusedIndex].value);
          }
          break;
        case 'Escape':
          event.preventDefault();
          setIsOpen(false);
          triggerRef.current?.focus();
          break;
        case 'ArrowDown':
          event.preventDefault();
          if (!isOpen) {
            setIsOpen(true);
            const selectedIdx = options.findIndex((opt) => opt.value === value);
            setFocusedIndex(selectedIdx >= 0 ? selectedIdx : 0);
          } else {
            setFocusedIndex((prev) => (prev < options.length - 1 ? prev + 1 : prev));
          }
          break;
        case 'ArrowUp':
          event.preventDefault();
          if (isOpen) {
            setFocusedIndex((prev) => (prev > 0 ? prev - 1 : prev));
          }
          break;
        case 'Home':
          event.preventDefault();
          if (isOpen) {
            setFocusedIndex(0);
          }
          break;
        case 'End':
          event.preventDefault();
          if (isOpen) {
            setFocusedIndex(options.length - 1);
          }
          break;
        case 'Tab':
          if (isOpen) {
            setIsOpen(false);
          }
          break;
      }
    },
    [disabled, isOpen, focusedIndex, options, value, handleSelect]
  );

  // Handle mouse leave to close dropdown
  const handleMouseLeave = () => {
    if (isOpen) {
      setIsOpen(false);
    }
  };

  return (
    <div
      ref={containerRef}
      className={`${styles.selectContainer} ${className}`}
      id={id}
      onMouseLeave={handleMouseLeave}
    >
      {/* Trigger Button */}
      <button
        ref={triggerRef}
        type="button"
        className={`${styles.trigger} ${isOpen ? styles.triggerOpen : ''} ${disabled ? styles.triggerDisabled : ''}`}
        onClick={handleToggle}
        onKeyDown={handleKeyDown}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-disabled={disabled}
        disabled={disabled}
      >
        <span className={styles.triggerText}>
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <span className={`${styles.arrow} ${isOpen ? styles.arrowOpen : ''}`}>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
            <path d="M6 9L1 4h10z" />
          </svg>
        </span>
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <ul
          ref={listRef}
          className={styles.menu}
          role="listbox"
          aria-activedescendant={focusedIndex >= 0 ? `option-${focusedIndex}` : undefined}
          tabIndex={-1}
        >
          {options.map((option, index) => {
            const isSelected = option.value === value;
            const isFocused = index === focusedIndex;

            return (
              <li
                key={option.value}
                id={`option-${index}`}
                role="option"
                aria-selected={isSelected}
                tabIndex={-1}
                className={`${styles.option} ${isSelected ? styles.optionSelected : ''} ${isFocused ? styles.optionFocused : ''}`}
                onClick={() => handleSelect(option.value)}
                onMouseEnter={() => setFocusedIndex(index)}
                onKeyDown={handleKeyDown}
              >
                {option.label}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
