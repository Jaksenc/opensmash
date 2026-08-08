# Mesh generation strategy eval — Napoleon Bonaparte test (2026-08-07)

| Strategy | Result | Verdict |
|---|---|---|
| A: text → Meshy text-to-3D | Good likeness, **ignored T-pose** (hands clasped), untextured preview | ✗ pose control unreliable |
| B1: GPT-Image-2 T-pose sheet → Meshy image-to-3D | Perfect T-pose, fully textured, clean geometry | ✓ **WINNER** |
| B2: Gemini 3.1 Flash Image → Meshy image-to-3D | Good, chunkier N64 style, but bent arms + podium reconstructed into mesh | ~ usable with prompt fixes |

Prompt rules learned: demand "strict T-pose, arms perfectly horizontal", "plain white background", "no floor, no podium, no pedestal", "full body centered". Image model quality transfers directly to mesh quality.

Files: napoleon-{A,B1,B2}*.{glb,png}; task ids in this dir's history. ~20 Meshy credits + ~$0.15 total.
