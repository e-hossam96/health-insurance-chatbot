import type { ReactNode } from 'react';
import Markdown from 'react-markdown';

export function MarkdownContent({ content }: { content: string }): ReactNode {
  return (
    <div dir="auto" className="markdown-content space-y-2 [&_ol]:list-decimal [&_ol]:ps-5 [&_ul]:list-disc [&_ul]:ps-5" data-testid="markdown-content">
      <Markdown skipHtml>{content}</Markdown>
    </div>
  );
}
