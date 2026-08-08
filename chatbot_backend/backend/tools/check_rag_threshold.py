"""
Calibration helper for RAG_MAX_DISTANCE.

The "knowledge found?" branch turns on a distance threshold, and the right value
shifts as terminology is added to the knowledge base. Run this after seeding a
batch of new terms to check the two groups below are still cleanly separated.

    venv\\Scripts\\python -m backend.tools.check_rag_threshold

Add your own questions to the lists as the knowledge base grows: DOCUMENTED are
questions the terminology *should* cover, UNDOCUMENTED are ones it should not.
A good threshold sits between the worst DOCUMENTED score and the best
UNDOCUMENTED one.
"""

from backend.config import RAG_MAX_DISTANCE
from backend.tools.vector_tools import _embeddings, get_collection, is_available

DOCUMENTED = [
    "what is our consumption trend for steel",
    "demurrage risk on containers",
    "which items are below reorder level",
    "how much has ETA slipped on our imports",
    "which suppliers deliver late",
    "what is the landed cost of imported items",
    "how many export documents are pending per party",
    "how many vehicles did each transporter use last month",
    "what is the average gross weight per packing job",
]

UNDOCUMENTED = [
    "which customers changed their payment terms this year",
    "what is the scrap rate per production job",
    "how long does bank approval take on average",
    "who is the tallest person in the office",
]


def _best_distance(collection, question: str) -> tuple[float, str]:
    result = collection.query(
        query_embeddings=[_embeddings().embed_query(question)],
        n_results=3,
        where={"kind": "term"},
    )
    distances = result["distances"][0]
    documents = result["documents"][0]
    if not distances:
        return float("inf"), "(nothing)"
    best = min(range(len(distances)), key=lambda i: distances[i])
    return distances[best], documents[best].splitlines()[0][:50]


def main() -> None:
    collection = get_collection()
    if collection is None or not is_available():
        print("Vector store is empty. Seed it first:")
        print("  venv\\Scripts\\python -m backend.tools.vector_tools")
        return

    print(f"Current RAG_MAX_DISTANCE = {RAG_MAX_DISTANCE}\n")

    worst_documented = 0.0
    best_undocumented = float("inf")

    for label, questions in (("DOCUMENTED", DOCUMENTED), ("UNDOCUMENTED", UNDOCUMENTED)):
        print(f"--- {label} ---")
        for question in questions:
            distance, match = _best_distance(collection, question)
            found = distance <= RAG_MAX_DISTANCE
            # A documented question that is not found, or an undocumented one
            # that is, means the threshold is in the wrong place.
            expected = (label == "DOCUMENTED")
            flag = "  <-- WRONG" if found != expected else ""
            verdict = "found" if found else "knowledge agent"
            print(f"  {distance:.3f}  {verdict:<16} {question[:46]:<48} | {match}{flag}")

            if label == "DOCUMENTED":
                worst_documented = max(worst_documented, distance)
            else:
                best_undocumented = min(best_undocumented, distance)
        print()

    print(f"worst documented   : {worst_documented:.3f}")
    print(f"best undocumented  : {best_undocumented:.3f}")

    if worst_documented < best_undocumented:
        midpoint = (worst_documented + best_undocumented) / 2
        print(f"\nGroups separate cleanly. Suggested RAG_MAX_DISTANCE = {midpoint:.2f}")
    else:
        print(
            "\nGroups OVERLAP - no threshold separates them. Either a DOCUMENTED "
            "question needs a terminology entry, or an UNDOCUMENTED one is closer "
            "to an existing term than expected."
        )


if __name__ == "__main__":
    main()
