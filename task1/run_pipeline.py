"""Run the Task 1 pipeline."""
from pipeline.run import run_pipeline

if __name__ == "__main__":
    path = run_pipeline()
    print(f"Pipeline complete. Analytics written to {path}")
