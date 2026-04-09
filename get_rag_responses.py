import json
import time
import os
import sys
import io
from pathlib import Path
from dotenv import load_dotenv

# Use the encoding set by rag.py or system defaults
from rag import RAGEngine

def main(limit=10):
    load_dotenv()
    
    # Initialize RAG
    print("🤖 Initializing RAG Engine...")
    engine = RAGEngine()
    engine.build_embeddings() # Ensure embeddings are loaded from cache
    
    dataset_path = Path("ragas_dataset_20.json")
    if not dataset_path.exists():
        print(f"❌ Dataset not found: {dataset_path}")
        return

    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    samples = data["samples"][:limit]
    
    eval_samples = []
    print(f"🚀 Generating RAG responses for {len(samples)} samples...")
    
    for i, s in enumerate(samples):
        query = s["user_input"]
        print(f"\n[{i+1}/{len(samples)}] Query: {query}")
        
        try:
            # 1. Get Top-K Contexts (raw text for Ragas)
            docs = engine.retrieve(query)
            contexts = [d["text"] for d in docs]
            
            # 2. Get Answer from RAG Pipeline
            result = engine.answer(query)
            
            eval_samples.append({
                "user_input": query,
                "response": result["text"],
                "retrieved_contexts": contexts,
                "reference": s["reference"]
            })
            print(f"   ✅ Answer received ({result['total_tokens']} tokens)")
            
        except Exception as e:
            print(f"   ❌ Error processing sample: {e}")
            continue
            
        # Cooldown to stay within Gemini Free Tier limits
        if i < len(samples) - 1:
            print(f"   ⏳ Cooldown 10s to respect API rate limits...")
            time.sleep(10)
            
    output_path = Path("ragas_dataset_trial.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"samples": eval_samples}, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Trial dataset for evaluation saved to: {output_path}")

if __name__ == "__main__":
    # Standard limit of 10 for trial
    main(limit=10)
