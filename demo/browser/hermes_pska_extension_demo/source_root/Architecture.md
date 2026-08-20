# PSKA Hermes Extension Architecture

PSKA is not an independent frontend. In the demo product shape, Hermes WebUI is the visible workspace and PSKA is the glue layer behind it.

The PSKA Mini extension inside Hermes WebUI exposes a thin control plane: runtime scope, Jarvis Briefing, Agentic Context Brief, Source Recall, Memory Review, and projection to Hermes Kanban or Tasks.

Source Recall is metadata-first and does not require embedding. It searches registered local source roots by title, path, extracted text, and structured metadata. This makes it suitable for personal folders where the user wants management, recall, deduplication, tags, comments, and audit trails before any semantic vector layer is introduced.

The durable architecture boundary is:

- Hermes WebUI owns chat, sessions, extension loading, task views, and the user's daily operating surface.
- PSKA Product API owns source registry, memory review gates, trace summaries, evidence packets, and agentic context assembly.
- PSKA MCP HTTP exposes the same capabilities to Hermes agents as tools.
- Eidolia remains a WebUI-embedded creation workspace with thoughts and artifacts; PSKA reads its trace/context instead of becoming a separate Eidolia frontend.

For a PSKA answer, the agent should cite source recall, memory, trace, and next actions instead of pretending that a standalone Ask page is the product.
