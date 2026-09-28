import ReactMarkdown from "react-markdown";

export function MessageContent({ text }: { text: string }) {
  return <div className="message-markdown"><ReactMarkdown skipHtml allowedElements={["p", "strong", "em", "ul", "ol", "li", "code", "br"]}>{text}</ReactMarkdown></div>;
}
