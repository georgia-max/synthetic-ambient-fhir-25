"""4-connected BFS pathfinding over a collision grid.

Mirrors the original ``path_finder`` contract: the grid is indexed ``[y][x]``,
``start``/``end`` are ``(x, y)`` tuples, cells equal to ``collision_block_char``
are walls, and the result is an ordered list of ``(x, y)`` tiles from start to
end inclusive (empty if unreachable). BFS gives a shortest path, matching the
wavefront expansion the original used.
"""
from __future__ import annotations

from collections import deque


def path_finder(maze, start, end, collision_block_char, verbose=False):
    """Return the shortest 4-connected path start..end inclusive, or []."""
    height = len(maze)
    width = len(maze[0]) if height else 0

    def walkable(x, y):
        return 0 <= x < width and 0 <= y < height and maze[y][x] != collision_block_char

    sx, sy = start
    ex, ey = end
    if not walkable(sx, sy) or not walkable(ex, ey):
        return []
    if (sx, sy) == (ex, ey):
        return [(sx, sy)]

    prev: dict[tuple[int, int], tuple[int, int]] = {}
    seen = {(sx, sy)}
    q = deque([(sx, sy)])
    while q:
        x, y = q.popleft()
        if (x, y) == (ex, ey):
            break
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            nx, ny = x + dx, y + dy
            if walkable(nx, ny) and (nx, ny) not in seen:
                seen.add((nx, ny))
                prev[(nx, ny)] = (x, y)
                q.append((nx, ny))

    if (ex, ey) not in seen:
        return []

    path = [(ex, ey)]
    while path[-1] != (sx, sy):
        path.append(prev[path[-1]])
    path.reverse()
    return path


def closest_coordinate(curr, targets):
    """Return the target tile with the smallest Euclidean distance to ``curr``."""
    best = None
    best_d = None
    for c in targets:
        d = ((c[0] - curr[0]) ** 2 + (c[1] - curr[1]) ** 2) ** 0.5
        if best is None or d < best_d:
            best, best_d = c, d
    return best
