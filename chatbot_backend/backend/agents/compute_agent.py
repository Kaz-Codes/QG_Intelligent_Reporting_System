"""
Computation agent - the assistant's dynamic tool.

For a question that SQL fetched data for but cannot itself answer (a correlation,
a variability measure, a custom score), this agent writes a Python snippet,
validates and runs it in the sandbox over the query results, and hands the
computed value to the response agent.

It owns its own retry loop (unlike the SQL agent, which loops through the graph):
on a sandbox rejection or runtime error it feeds the error back to the model and
regenerates, up to COMPUTE_MAX_RETRIES. That keeps the graph simple - this is a
single node in, single node out.

Gated by ENABLE_COMPUTE. When off, the node is never wired into the graph.
"""

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.config import COMPUTE_MAX_RETRIES, COMPUTE_TIMEOUT_S, EFFORT_ACCURATE, structured_llm
from backend.prompts.compute_prompt import COMPUTE_SYSTEM_PROMPT, build_compute_prompt
from backend.tools.sandbox import SafeExecutionError, run_code


class GeneratedComputation(BaseModel):
    code: str = Field(description="Python that assigns the answer to `result`.")
    explanation: str = Field(description="One line on what the code computes.")


def compute_agent(state: dict) -> dict:
    question = state.get("rewritten_query") or state.get("user_query", "")
    task = state.get("computation_task") or question
    rows = state.get("retrieved_data") or []
    columns = state.get("columns") or (list(rows[0].keys()) if rows else [])

    llm = structured_llm(GeneratedComputation, effort=EFFORT_ACCURATE)

    previous_code = ""
    error = ""

    # generate -> run -> on failure feed the error back, up to the retry budget.
    for attempt in range(COMPUTE_MAX_RETRIES + 1):
        try:
            generated = llm.invoke(
                [
                    SystemMessage(content=COMPUTE_SYSTEM_PROMPT),
                    HumanMessage(
                        content=build_compute_prompt(
                            task, question, columns, rows, previous_code, error
                        )
                    ),
                ]
            )
        except Exception as exc:
            return {"computation_error": f"Could not generate computation: {exc}"}

        try:
            result = run_code(generated.code, rows, timeout=COMPUTE_TIMEOUT_S)
        except SafeExecutionError as exc:
            previous_code = generated.code
            error = str(exc)
            continue  # retry with the error fed back

        return {
            "computation_code": generated.code,
            "computation_explanation": generated.explanation,
            "computation_result": result,
            "computation_attempts": attempt + 1,
            "computation_error": "",
        }

    # Exhausted retries - let the response agent explain the limitation.
    return {
        "computation_code": previous_code,
        "computation_error": f"Computation failed after {COMPUTE_MAX_RETRIES + 1} attempt(s): {error}",
        "computation_attempts": COMPUTE_MAX_RETRIES + 1,
    }
