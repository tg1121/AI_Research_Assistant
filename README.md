# Research Paper Assistant

Agentic RAG for research papers, with separate pipelines for math-heavy and general content.

How it works

Uploaded PDFs are auto-classified. Math heavy papers go through a regex knowledge graph (theorems, lemmas, proofs) + equation chain extraction. General papers use TF-IDF + section-sampled synthesis. Both feed into a ReAct agent with four tools: document map, section retrieval, reference traversal, and concept search.

Multi-provider LLM routing via LiteLLM. Sliding window memory with LLM-compressed summaries.

Stack

FastAPI · React · LiteLLM · Supabase
