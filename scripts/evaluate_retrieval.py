from statistics import mean

from app.repositories.chunk_repository import semantic_search_chunks


DOCUMENT_ID = 9

EVAL_CASES = [
    {
        "question": "Who is the main character?",
        "expected_chunks": {115, 158, 168, 65},
    },
    {
        "question": "Who is Wheeler?",
        "expected_chunks": {66, 68, 80, 126, 163},
    },
    {
        "question": "Who is Marion?",
        "expected_chunks": {43, 180, 181},
    },
    {
        "question": "What happens to Wheeler?",
        "expected_chunks": {115, 158, 168},
    },
    {
        "question": "What is SCP-3125?",
        "expected_chunks": {50, 59, 132},
    },
    {
        "question": "Who is Gauss?",
        "expected_chunks": {67, 68},
    },
    {
        "question": "Who is Hughes?",
        "expected_chunks": {164, 145, 141},
    },
    {
        "question": "What happens at Site 41?",
        "expected_chunks": {161, 12, 61},
    },
    {
        "question": "What happened to Marion?",
        "expected_chunks": {43, 46, 70, 181},
    },
    {
        "question": "What is Wheeler trying to do?",
        "expected_chunks": {163, 162, 108},
    },
]
THRESHOLDS = [0.20, 0.25, 0.28, 0.30]


def hit_at_k(results, expected_chunks, k):
    top_chunks = {
        result["chunk_index"]
        for result in results[:k]
    }

    return bool(top_chunks & expected_chunks)


def evaluate():
    hit_1_scores = []
    hit_3_scores = []
    hit_5_scores = []
    top_similarities = []

    for case in EVAL_CASES:
        question = case["question"]
        expected_chunks = case["expected_chunks"]

        results = semantic_search_chunks(
            document_id=DOCUMENT_ID,
            query=question,
            limit=5,
        )

        hit_1 = hit_at_k(
            results,
            expected_chunks,
            1,
        )
        hit_3 = hit_at_k(
            results,
            expected_chunks,
            3,
        )
        hit_5 = hit_at_k(
            results,
            expected_chunks,
            5,
        )

        hit_1_scores.append(hit_1)
        hit_3_scores.append(hit_3)
        hit_5_scores.append(hit_5)

        if results:
            top_similarities.append(
                results[0]["similarity"]
            )

        print(f"\nQuestion: {question}")
        print(f"Hit@1: {hit_1}")
        print(f"Hit@3: {hit_3}")
        print(f"Hit@5: {hit_5}")

        for result in results:
            preview = result["chunk_text"][:250].replace("\n", " ")

            print(
                f"  chunk={result['chunk_index']} "
                f"similarity={result['similarity']}"
            )

            print(f"    {preview}")

    print("\n=== Retrieval Evaluation ===")

    print(
        f"Hit@1: "
        f"{mean(hit_1_scores):.2%}"
    )

    print(
        f"Hit@3: "
        f"{mean(hit_3_scores):.2%}"
    )

    print(
        f"Hit@5: "
        f"{mean(hit_5_scores):.2%}"
    )

    if top_similarities:
        print(
            f"Average top similarity: "
            f"{mean(top_similarities):.4f}"
        )
def evaluate_thresholds():
    print("\n=== Threshold Evaluation ===")

    for threshold in THRESHOLDS:
        hit_3_scores = []
        accepted_counts = []

        for case in EVAL_CASES:
            results = semantic_search_chunks(
                document_id=DOCUMENT_ID,
                query=case["question"],
                limit=5,
            )

            filtered_results = [
                result
                for result in results
                if result["similarity"] >= threshold
            ]

            hit_3 = hit_at_k(
                filtered_results,
                case["expected_chunks"],
                3,
            )

            hit_3_scores.append(hit_3)
            accepted_counts.append(len(filtered_results))

        print(
            f"threshold={threshold:.2f} "
            f"Hit@3={mean(hit_3_scores):.2%} "
            f"avg_chunks={mean(accepted_counts):.2f}"
        )
if __name__ == "__main__":
    evaluate()
    evaluate_thresholds()