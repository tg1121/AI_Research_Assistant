import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

// remark-math only handles $...$ and $$...$$
// LLMs often output \[...\] (block) and \(...\) (inline) — normalise those here.
function normalizeMath(text) {
  return text
    .replace(/\\\[/g, '\n$$\n')
    .replace(/\\\]/g, '\n$$\n')
    .replace(/\\\(/g, '$')
    .replace(/\\\)/g, '$');
}

export default function Md({ children, style }) {
  return (
    <div className="md" style={style}>
      <ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[rehypeKatex]}>
        {normalizeMath(String(children ?? ''))}
      </ReactMarkdown>
    </div>
  );
}
