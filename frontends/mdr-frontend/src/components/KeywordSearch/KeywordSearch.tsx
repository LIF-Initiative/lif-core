import React, { useMemo, useState, useCallback } from "react";
import "./KeywordSearch.css";

export interface KeywordSearchItem {
    id: string | number;
    label: string;
    // Optional target to scroll to (e.g., attribute id in the column list)
    scrollId?: number;
    // Optional kind for styling/analytics; not used functionally here
    kind?: 'entity' | 'attribute' | string;
}

export interface KeywordSearchProps {
    // Data to search
    items: KeywordSearchItem[];

    // Selection callback when user cycles/selects a match
    onSelect?: (item: KeywordSearchItem, index: number) => void;

    // Notifies when the list of results changes (e.g., query/toggles/items update)
    onResultsChange?: (matches: KeywordSearchItem[]) => void;

    // Optional aria/id hooks
    id?: string;
    className?: string;
}

function escapeRegExp(s: string) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function makeMatcher(query: string, matchCase: boolean, wholeWord: boolean) {
    if (!query) {
        return () => true;
    }
    let q = query;
    const flags = matchCase ? '' : 'i';
    if (wholeWord) {
        try {
            const re = new RegExp(`\\b${escapeRegExp(q)}\\b`, flags);
            return (label: string) => re.test(label);
        } catch {
            // Fallback to includes when regex fails
        }
    }
    if (!matchCase) q = q.toLowerCase();
    return (label: string) => {
        const text = matchCase ? label : label.toLowerCase();
        return text.includes(q);
    };
}

export const KeywordSearch: React.FC<KeywordSearchProps> = ({
    items,
    onSelect,
    onResultsChange,
    id,
    className,
}) => {
    const [query, setQuery] = useState('');
    const [index, setIndex] = useState(0);
    const [matchCase, setMatchCase] = useState(false);
    const [wholeWord, setWholeWord] = useState(false);

    const matcher = useMemo(
        () => makeMatcher(query.trim(), matchCase, wholeWord),
        [query, matchCase, wholeWord]
    );

    const matches = useMemo(() => {
        if (!query.trim()) return [] as KeywordSearchItem[];
        return items.filter((it) => matcher(it.label));
    }, [items, matcher, query]);

    // Keep index in range when matches change
    const clampedIndex = matches.length
        ? Math.min(Math.max(index, 0), matches.length - 1)
        : 0;

    // Notify selection when query or index changes
    React.useEffect(() => {
        if (matches.length && onSelect) {
            onSelect(matches[clampedIndex], clampedIndex);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [clampedIndex, matches.length]);

    const cycle = useCallback(
        (delta: number) => {
            if (!matches.length) return;
            const next = (clampedIndex + delta + matches.length) % matches.length;
            setIndex(next);
            if (onSelect) onSelect(matches[next], next);
        },
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [clampedIndex, matches]
    );

    const clear = useCallback(() => {
        setQuery('');
        setIndex(0);
    }, []);

    const onInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter') {
            // Move to next match on Enter
            e.preventDefault();
            cycle(1);
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            cycle(1);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            cycle(-1);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            clear();
        }
    };

    const status = !query.trim()
        ? ''
        : matches.length === 0
        ? 'no results'
        : `${clampedIndex + 1} out of ${matches.length}`;

    // Inform parent when result set changes
    React.useEffect(() => {
        if (onResultsChange) onResultsChange(matches);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [matches]);

    return (
        <div className={`keyword-search ${className ?? ''}`} data-component="keyword-search" id={id}>
            <input
                className="mappings-column__search"
                type="text"
                placeholder="Search by name"
                value={query}
                onChange={(e) => {
                    setIndex(0);
                    setQuery(e.target.value);
                }}
                onKeyDown={onInputKeyDown}
            />
            <span className="keyword-search__status">
                {status}
            </span>
            {matches.length > 1 && (
                <span className="keyword-search__nav">
                    <button
                        type="button"
                        className="keyword-search__btn keyword-search__btn--prev"
                        title="Previous match"
                        onClick={() => cycle(-1)}
                    >
                        ↑
                    </button>
                    <button
                        type="button"
                        className="keyword-search__btn keyword-search__btn--next"
                        title="Next match"
                        onClick={() => cycle(1)}
                    >
                        ↓
                    </button>
                </span>
            )}
            <button
                type="button"
                className="keyword-search__btn keyword-search__btn--matchcase"
                title="Match case"
                onClick={() => setMatchCase((v) => !v)}
                data-active={matchCase ? 'true' : 'false'}
            >
                Aa
            </button>
            <button
                type="button"
                className="keyword-search__btn keyword-search__btn--wholeword"
                title="Match whole word"
                onClick={() => setWholeWord((v) => !v)}
                data-active={wholeWord ? 'true' : 'false'}
            >
                W
            </button>
            <button
                type="button"
                className="keyword-search__btn keyword-search__btn--clear"
                title="Clear"
                onClick={clear}
            >
                ×
            </button>
        </div>
    );
};

export default KeywordSearch;
