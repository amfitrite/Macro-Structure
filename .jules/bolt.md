## 2024-05-15 - [Ranking Performance]
**Learning:** Found an O(N^2) loop in `trader-screener/screen.py` when calculating ranks by iterating over `ordered` list twice for every element in `vals`. This can be heavily optimized using binary search (`bisect`) to O(N log N).
**Action:** Replaced O(N^2) iteration with `bisect` for determining below/equal count in ranking logic.
