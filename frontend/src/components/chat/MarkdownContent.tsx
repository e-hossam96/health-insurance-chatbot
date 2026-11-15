import type { ReactNode } from 'react';
import Markdown from 'react-markdown';

export function MarkdownContent({ content }: { content: string }): ReactNode {
  return (
    <div className="markdown-content space-y-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_a]:underline [&_code]:rounded [&_code]:bg-gray-200 [&_code]:px-1" data-testid="markdown-content">
      <Markdown skipHtml>{content}</Markdown>
    </div>
  );
}
