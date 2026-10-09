import React from "react";
import KeywordSearch from "@/components/KeywordSearch/KeywordSearch";
import type { KeywordSearchItem } from "@/components/KeywordSearch/KeywordSearch";

interface ColumnHeaderProps {
  side: 'left' | 'right';
  title: string;
  headerNameNode?: React.ReactNode;
  scrollRef: React.RefObject<HTMLDivElement>;
  searchItems?: KeywordSearchItem[];
  query: string;
  onQueryChange: (q: string) => void;
}

const ColumnHeader: React.FC<ColumnHeaderProps> = ({
  side,
  title,
  headerNameNode,
  scrollRef,
  searchItems,
}) => {
  return (
    <div className="mappings-column">
      <div className="mappings-column__cap">
        <div className="mappings-column__header" data-side={side}>
          <span className="mappings-column__header-label">
            {side === 'left' ? 'Source Data Model' : 'Target Data Model'}:
          </span>
          <span className="mappings-column__header-name">{headerNameNode ?? (title || 'Loading…')}</span>
        </div>
        <KeywordSearch
          className="mappings-column__search-wrap"
          items={searchItems || []}
          onResultsChange={(results) => {
            const scroller = scrollRef.current;
            if (!scroller) return;
            // Clear previous highlights
            scroller
              .querySelectorAll('.mappings-highlight')
              .forEach((el) => {
                const parent = el.parentNode as HTMLElement | null;
                if (!parent) return;
                parent.replaceChild(document.createTextNode(el.textContent || ''), el);
                parent.normalize();
              });
            if (!results.length) return;
            const byAttr = new Set(
              results
                .filter((r) => r.kind === 'attribute' && r.scrollId != null)
                .map((r) => String(r.scrollId))
            );
            const byEntity = new Set(
              results
                .filter((r) => r.kind === 'entity' && r.scrollId != null)
                .map((r) => String(r.scrollId))
            );
            byEntity.forEach((id) => {
              const container = scroller.querySelector(
                `[data-entity-id="${id}"] .mappings-entity__name`
              ) as HTMLElement | null;
              if (container) {
                const text = container.textContent || '';
                container.textContent = '';
                const span = document.createElement('span');
                span.className = 'mappings-highlight';
                span.textContent = text;
                container.appendChild(span);
              }
            });
            byAttr.forEach((id) => {
              const container = scroller.querySelector(
                `[data-attr-id="${id}"] .mappings-attr__name`
              ) as HTMLElement | null;
              if (container) {
                const text = container.textContent || '';
                container.textContent = '';
                const span = document.createElement('span');
                span.className = 'mappings-highlight';
                span.textContent = text;
                container.appendChild(span);
              }
            });
          }}
          onSelect={(item) => {
            const scroller = scrollRef.current;
            if (!scroller) return;
            let el: HTMLElement | null = null;
            if (item.kind === 'attribute' && item.scrollId != null) {
              el = scroller.querySelector(`[data-attr-id="${item.scrollId}"]`) as HTMLElement | null;
            } else if (item.kind === 'entity' && item.scrollId != null) {
              el = scroller.querySelector(`[data-entity-id="${item.scrollId}"]`) as HTMLElement | null;
            }
            if (el) {
              const scrollRect = scroller.getBoundingClientRect();
              const elRect = el.getBoundingClientRect();
              const offset = elRect.top - scrollRect.top;
              scroller.scrollTop += offset - scrollRect.height / 2 + elRect.height / 2;
              const pulseTarget = (
                (item.kind === 'attribute'
                  ? el.querySelector('.mappings-attr__name .mappings-highlight')
                  : el.querySelector('.mappings-entity__name .mappings-highlight')) ||
                (item.kind === 'attribute'
                  ? el.querySelector('.mappings-attr__name')
                  : el.querySelector('.mappings-entity__name'))
              ) as HTMLElement | null;
              if (pulseTarget) {
                pulseTarget.classList.remove('mappings-pulse');
                // force reflow to restart animation
                (pulseTarget as any).offsetWidth;
                pulseTarget.classList.add('mappings-pulse');
              }
            }
          }}
        />
      </div>
    </div>
  );
};

export default ColumnHeader;
