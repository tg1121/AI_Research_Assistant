import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

export default function Md({ children, style }) {
  return (
    <div className="md" style={style}>
      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
        {String(children ?? '')}
      </ReactMarkdown>
    </div>
  );
}
