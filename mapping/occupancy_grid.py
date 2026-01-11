# mapping/occupancy_grid.py

import math
from typing import List, Tuple, Optional

from PIL import Image, ImageDraw

import config


UNKNOWN = -1
FREE = 0
OCCUPIED = 1


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def bresenham(x0, y0, x1, y1):
    """
    Bresenham line algorithm between two grid cells.
    Returns list of (x, y) points including both endpoints.
    """
    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    x, y = x0, y0
    sx = 1 if x1 >= x0 else -1
    sy = 1 if y1 >= y0 else -1

    if dy <= dx:
        err = dx / 2.0
        while x != x1:
            points.append((x, y))
            err -= dy
            if err < 0:
                y += sy
                err += dx
            x += sx
        points.append((x1, y1))
    else:
        err = dy / 2.0
        while y != y1:
            points.append((x, y))
            err -= dx
            if err < 0:
                x += sx
                err += dy
            y += sy
        points.append((x1, y1))
    return points


class OccupancyGrid:
    """
    2D occupancy grid with last scan point overlay.
    Grid is centered at (0,0) in cm; extent is +/- MAP_HALF_CM.
    """
    def __init__(self):
        self.size = config.MAP_CELLS
        self.cell_cm = config.CELL_CM
        self.half_cm = config.MAP_HALF_CM

        # row-major [r][c]
        self.grid = [[UNKNOWN for _ in range(self.size)] for __ in range(self.size)]
        self.last_points_global_cm: List[Tuple[float, float]] = []

    def reset(self):
        self.grid = [[UNKNOWN for _ in range(self.size)] for __ in range(self.size)]
        self.last_points_global_cm = []

    def _world_to_cell(self, x_cm: float, y_cm: float) -> Optional[Tuple[int, int]]:
        """
        Convert world cm -> (col, row) indices.
        row 0 at top (y=+half), row increases downward.
        """
        if x_cm < -self.half_cm or x_cm > self.half_cm or y_cm < -self.half_cm or y_cm > self.half_cm:
            return None

        col = int((x_cm + self.half_cm) / self.cell_cm)
        row = int((self.half_cm - y_cm) / self.cell_cm)

        col = clamp(col, 0, self.size - 1)
        row = clamp(row, 0, self.size - 1)
        return (col, row)

    def update_with_scan(self, pose, scan_points_robot_cm: List[Tuple[float, float]]):
        """
        pose: (x_cm, y_cm, theta_rad) in world frame
        scan_points_robot_cm: list of (x_cm, y_cm) endpoints in robot frame (relative)
        """
        x0, y0, th = pose
        origin_cell = self._world_to_cell(x0, y0)
        if origin_cell is None:
            # pose out of map; ignore
            return

        ox, oy = origin_cell
        last_pts = []

        # Robot-to-world rotation (theta=0 means facing +y)
        ct = math.cos(th)
        st = math.sin(th)

        for (rx, ry) in scan_points_robot_cm:
            # Transform to world
            wx = x0 + (rx * ct + ry * st)
            wy = y0 + (-rx * st + ry * ct)

            # Clip points outside map: still raycast to boundary as free, but no occupied endpoint
            end_cell = self._world_to_cell(wx, wy)

            if end_cell is None:
                # find boundary intersection by scaling vector
                # approximate: step along ray until inside boundary
                # If far away, we can skip endpoint occupancy but mark free along clipped endpoint.
                # Simple approach: clamp wx/wy to map bounds.
                wx_clamped = clamp(wx, -self.half_cm, self.half_cm)
                wy_clamped = clamp(wy, -self.half_cm, self.half_cm)
                end_cell = self._world_to_cell(wx_clamped, wy_clamped)
                if end_cell is None:
                    continue
                # Do not mark occupied when clamped
                mark_occupied = False
                wx, wy = wx_clamped, wy_clamped
            else:
                mark_occupied = True

            ex, ey = end_cell
            line = bresenham(ox, oy, ex, ey)

            # mark FREE along ray excluding last cell
            for (cx, cy) in line[:-1]:
                self.grid[cy][cx] = FREE

            # endpoint
            if mark_occupied:
                self.grid[ey][ex] = OCCUPIED

            last_pts.append((wx, wy))

        self.last_points_global_cm = last_pts

    def render_png(self, pose, out_path: str):
        """
        Render occupancy grid with rover pose and last scan points overlay.
        """
        img_w = self.size * config.RENDER_SCALE
        img_h = self.size * config.RENDER_SCALE

        img = Image.new("RGB", (img_w, img_h), (220, 220, 220))
        draw = ImageDraw.Draw(img)

        # Draw cells
        for r in range(self.size):
            for c in range(self.size):
                v = self.grid[r][c]
                if v == UNKNOWN:
                    color = (200, 200, 200)
                elif v == FREE:
                    color = (245, 245, 245)
                else:
                    color = (0, 0, 0)

                x0 = c * config.RENDER_SCALE
                y0 = r * config.RENDER_SCALE
                x1 = x0 + config.RENDER_SCALE - 1
                y1 = y0 + config.RENDER_SCALE - 1
                draw.rectangle([x0, y0, x1, y1], fill=color)

        # Overlay last scan points
        for (wx, wy) in self.last_points_global_cm:
            cell = self._world_to_cell(wx, wy)
            if cell is None:
                continue
            c, r = cell
            px = c * config.RENDER_SCALE + config.RENDER_SCALE // 2
            py = r * config.RENDER_SCALE + config.RENDER_SCALE // 2
            draw.ellipse([px-2, py-2, px+2, py+2], fill=(0, 90, 200))

        # Draw rover pose
        x_cm, y_cm, th = pose
        cell = self._world_to_cell(x_cm, y_cm)
        if cell is not None:
            c, r = cell
            px = c * config.RENDER_SCALE + config.RENDER_SCALE // 2
            py = r * config.RENDER_SCALE + config.RENDER_SCALE // 2
            draw.ellipse([px-4, py-4, px+4, py+4], fill=(200, 0, 0))

            # heading indicator
            hx = px + int(10 * math.sin(th))  # theta=0 => up (negative y), but our grid y increases down
            hy = py - int(10 * math.cos(th))
            draw.line([px, py, hx, hy], fill=(200, 0, 0), width=2)

        img.save(out_path)
