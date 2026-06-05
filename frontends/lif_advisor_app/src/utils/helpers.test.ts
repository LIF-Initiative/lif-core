import { describe, it, expect } from 'vitest';
import { extractOptions } from './helpers';

describe('extractOptions', () => {
  it('returns no options and unchanged text when there are no markers', () => {
    const { text, options } = extractOptions('Just a normal reply.');
    expect(options).toEqual([]);
    expect(text).toBe('Just a normal reply.');
  });

  it('extracts a trailing run of markers and strips them from the text', () => {
    const { text, options } = extractOptions('Would you like to explore?\n\n<<Yes>> <<No>>');
    expect(options).toEqual(['Yes', 'No']);
    expect(text).toBe('Would you like to explore?');
  });

  it('handles options inline at the end of a sentence', () => {
    const { text, options } = extractOptions('Pick one: <<Coursework>> <<Credentials>>');
    expect(options).toEqual(['Coursework', 'Credentials']);
    expect(text).toBe('Pick one:');
  });

  it('leaves markers that appear inside mid-message code untouched', () => {
    const content = 'Use `<<placeholder>>` in your template.\n\n<<Got it>>';
    const { text, options } = extractOptions(content);
    expect(options).toEqual(['Got it']);
    expect(text).toBe('Use `<<placeholder>>` in your template.');
  });

  it('does not extract markers when none are trailing', () => {
    const content = 'Set `key = <<value>>` and continue.';
    const { text, options } = extractOptions(content);
    expect(options).toEqual([]);
    expect(text).toBe('Set `key = <<value>>` and continue.');
  });

  it('preserves GFM hard line breaks (trailing two spaces) in the body', () => {
    const { text } = extractOptions('Line one.  \nLine two.\n\n<<Next>>');
    expect(text).toBe('Line one.  \nLine two.');
  });

  it('drops a dangling unclosed marker left by a truncated response', () => {
    const { text, options } = extractOptions('Want details? <<Yes>> <<Tell me mo');
    expect(options).toEqual(['Yes']);
    expect(text).toBe('Want details?');
  });

  it('de-duplicates options case-insensitively, keeping first-seen casing', () => {
    const { options } = extractOptions('<<Yes>> <<yes>> <<No>>');
    expect(options).toEqual(['Yes', 'No']);
  });

  it('handles a message that is only markers (empty body)', () => {
    const { text, options } = extractOptions('<<Yes>> <<No>>');
    expect(text).toBe('');
    expect(options).toEqual(['Yes', 'No']);
  });
});
