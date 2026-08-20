# Memory, Trace, And Next Actions

PSKA memory is governed memory, not a free-form personality summary. A candidate memory should preserve provenance, source references, confidence, lifecycle status, and whether it is fact, belief, decision, preference, or behavior delta.

The Hermes extension should surface memory review and next actions in the same place where the user is already talking to the agent. Jarvis Briefing provides workspace state and queues. Agentic Context Brief assembles evidence, source recall, memory candidates, trace, and next actions before a chat turn.

Trace should answer: what did the system look at, what did it infer, what did it write, and what should still require human review. Durable writes must stay behind PSKA gates.

This is the intended business case for the demo: a user asks why PSKA is a glue layer and not an independent frontend, then Hermes uses PSKA scope to recall local files and construct a grounded answer.
