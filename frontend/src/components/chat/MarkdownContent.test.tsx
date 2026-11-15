import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MarkdownContent } from './MarkdownContent';

describe('MarkdownContent', () => {
  it('F17: a script tag is not rendered', () => {
    const { container } = render(<MarkdownContent content={'<script>alert("xss")</script>\n\n**safe**'} />);
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('strong')?.textContent).toBe('safe');
  });

  it('F17: raw HTML elements and event handlers are not rendered', () => {
    const { container } = render(
      <MarkdownContent content={'<img src="x" onerror="alert(1)"> <b>bold</b> <iframe src="https://example.com"></iframe>'} />,
    );
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('b')).toBeNull();
    expect(container.querySelector('iframe')).toBeNull();
    expect(container.innerHTML).not.toContain('onerror');
  });

  it('F17: javascript links are neutralised', () => {
    const { container } = render(<MarkdownContent content={'[click](javascript:alert(1))'} />);
    const link = container.querySelector('a');
    expect(link?.getAttribute('href') ?? '').not.toContain('javascript');
  });

  it('F17: renders Markdown lists, bold and links', () => {
    const { container } = render(
      <MarkdownContent content={'- one\n- **two**\n\n[policy](https://example.com/policy)'} />,
    );
    expect(container.querySelectorAll('li')).toHaveLength(2);
    expect(container.querySelector('strong')?.textContent).toBe('two');
    expect(container.querySelector('a')?.getAttribute('href')).toBe('https://example.com/policy');
  });
});
