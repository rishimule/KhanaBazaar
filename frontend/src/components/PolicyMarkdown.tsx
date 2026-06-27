// Copyright (c) 2026 Rishi Mule. All Rights Reserved.
// This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";

/** Render admin-authored policy Markdown, sanitized (no raw HTML injection). */
export default function PolicyMarkdown({ body }: { body: string }) {
  return <ReactMarkdown rehypePlugins={[rehypeSanitize]}>{body}</ReactMarkdown>;
}
