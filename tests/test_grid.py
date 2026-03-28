from shapely.geometry import box

from edown.grid import (
    align_window_to_chunk,
    build_chunk_tasks,
    get_image_grid_info,
    intersection_to_pixel_bounds,
)
from tests.conftest import make_feature


def test_grid_window_and_chunk_tasks() -> None:
    feature = make_feature("IMG_1")
    grid = get_image_grid_info(feature)
    intersection = grid["bbox"].intersection(box(-0.5, -0.5, 0.5, 0.5))
    pixel_bounds = intersection_to_pixel_bounds(intersection, grid)
    assert pixel_bounds is not None
    window = align_window_to_chunk(pixel_bounds, grid, 4)
    tasks = build_chunk_tasks(*window, grid=grid, intersection=intersection, chunk_size=4)
    assert tasks
    assert window[1] > window[0]
    assert window[3] > window[2]


def test_intersection_to_pixel_bounds_supports_positive_y_scale() -> None:
    feature = make_feature("IMG_POS_Y", transform=(0.1, 0.0, -1.0, 0.0, 0.1, -1.0))
    grid = get_image_grid_info(feature)
    intersection = grid["bbox"].intersection(box(-0.5, -0.5, 0.5, 0.5))
    pixel_bounds = intersection_to_pixel_bounds(intersection, grid)

    assert pixel_bounds is not None
    assert pixel_bounds == (5, 15, 5, 15)
