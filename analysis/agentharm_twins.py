"""Which AgentHarm tools sit on both sides? Six lines of pandas over the public dataset.

    pip install datasets pandas
    python analysis/agentharm_twins.py

Source: ai-safety-institute/AgentHarm on Hugging Face (Andriushchenko et al., ICLR 2025),
split test_public, field `target_functions`. Nothing here calls Arcezia.
"""
from datasets import load_dataset

harmful  = load_dataset("ai-safety-institute/AgentHarm", "harmful",         split="test_public").to_pandas()
harmless = load_dataset("ai-safety-institute/AgentHarm", "harmless_benign", split="test_public").to_pandas()
th, tb = harmful["target_functions"].explode(), harmless["target_functions"].explode()
both, only_harmful = set(th) & set(tb), set(th) - set(tb)
print(f"tasks {len(harmful)} harmful / {len(harmless)} harmless | tool names {th.nunique()} / {tb.nunique()} | on both sides {len(both)} | harmful-only {sorted(only_harmful)}")
for t in ("get_webpage", "send_email", "post_on_x"):
    print(f"{t:12s} harmful {int((th == t).sum()):3d}  harmless {int((tb == t).sum()):3d}")
print("harmful tasks that use a harmful-only tool:", int(harmful["target_functions"].apply(lambda fs: any(f in only_harmful for f in fs)).sum()))
