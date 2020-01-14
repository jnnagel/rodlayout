from contextlib import contextmanager
from os import getenv
from typing import cast
from warnings import warn, simplefilter

import pytest
from attr import dataclass
from geometry import Rect, Segment, Point, Group
from pytest import fixture, raises, mark
from skillbridge import Workspace, current_workspace
from skillbridge.client.objects import RemoteObject

from rodlayout import Canvas, Layer
from rodlayout.handle import python_skill_handle
from rodlayout.hints import BoundingBox
from rodlayout.proxy import DbShape, Instance, RodShape, Figure

'''
This test package is skipped by default, unless env VIRTUOSO is set.

This test package requires a connected virtuoso instance. Furthermore:
A library named rodlayout_test with cells:
test_cell:
- Contains a P&R boundary constructed of points (-1 -3) (-1 5) (7 5) (7 -3).
- A rectangle; Left: 0; Bottom: 0; Right: 11; Top: 7.
test_layout:
- Should be opened (current cell view) and empty.
'''


@fixture
def ws():
    return Workspace.open().make_current()


@fixture
def cv():
    cv = current_workspace.db.open_cell_view_by_type(
        "rodlayout_test", "test_layout", "layout", "", "a"
    )
    return cv


@fixture
def cell_cv():
    return current_workspace.db.open_cell_view_by_type(
        "rodlayout_test", "test_cell", "layout", "", "a"
    )


@fixture
def canvas():
    return Canvas(current_workspace.ge.get_edit_cell_view())


pytestmark = mark.skipif(getenv("VIRTUOSO") is None, reason="no virtuoso tests")
saved_shapes = []


@fixture
def cleanup():
    try:
        yield None
    finally:
        for db in saved_shapes:
            try:
                db.delete(children=True)
            except Exception as e:
                simplefilter('always', UserWarning)
                warn(f"Failed to delete shape {db}: {e}", category=UserWarning, stacklevel=1)
                simplefilter('default', UserWarning)

        saved_shapes.clear()


def register_and_draw(self):
    shapes = self.pytest_saved_old_draw()
    saved_shapes.extend(shapes)
    return shapes


Canvas.pytest_saved_old_draw = Canvas.draw
Canvas.draw = register_and_draw


def point_equal(p1, p2):
    dx = abs(p1[0] - p2[0])
    dy = abs(p1[1] - p2[1])
    return dx < 1e-9 and dy < 1e-9


def layer_of(remote):
    lpp = remote.lpp
    if lpp is None and remote.db_id is not None:
        lpp = remote.db_id.lpp

    return None if lpp is None else Layer(*lpp)


def to_rect(r):
    if isinstance(r, Rect):
        return r
    (l, b), (right, t) = r.b_box or r.db_id.b_box

    return Rect.from_edges(l, right, b, t, layer_of(r))


def nearly_equal(x, y):
    if isinstance(x, (list, tuple)):
        return all(nearly_equal(xx, yy) for xx, yy in zip(x, y))
    return abs(x - y) < 1e-9


def rect_equal(r1, r2):
    r1 = to_rect(r1)
    r2 = to_rect(r2)

    return (
        nearly_equal(r1.bottom_left, r2.bottom_left)
        and nearly_equal(r1.top_right, r2.top_right)
        and r1.user_data == r2.user_data
    )


def to_segment(s):
    if isinstance(s, Segment):
        return s
    points = s.db_id.points if s.db_id else s.points
    width = s.db_id.width if s.db_id else s.width
    start, end = (Point(x, y) for x, y in points)
    return Segment.from_start_end(start, end, width, layer_of(s))


def segment_equal(s1, s2):
    s1 = to_segment(s1)
    s2 = to_segment(s2)

    return (
        nearly_equal(s1.start, s2.start)
        and nearly_equal(s1.end, s2.end)
        and nearly_equal(s1.thickness, s2.thickness)
        and s1.user_data == s2.user_data
    )


def test_cannot_draw_without_workspace():
    with raises(RuntimeError):
        Canvas()


def test_cannot_draw_without_layer(ws):
    with raises(AssertionError, match="layer"):
        c = Canvas()
        c.append(Rect[1, 2])
        c.draw()


def test_create_rect(ws, canvas, cleanup):
    layer = Layer('M1', 'drawing')
    r = Rect[0:0.1, 0.2:0.3, layer]

    canvas.append(r)
    (rod,) = canvas.draw()

    assert rod.valid
    assert rect_equal(r, rod.db)


def test_create_segment(ws, canvas, cleanup):
    layer = Layer('M2', 'pin')
    s = Segment.from_start_end(Point(0, 1), Point(10, 1), 2, layer)
    canvas.append(s)
    (rod,) = canvas.draw()

    assert rod.valid
    assert segment_equal(s, rod.db)


def test_create_group(ws, canvas, cleanup):
    r = Rect[0:0.1, 0.2:0.3, Layer('M1', 'drawing')]
    s = Segment.from_start_end(Point(1, 1), Point(2, 1), 0.1, Layer('M2', 'pin'))
    g = Group([r, s])

    canvas.append(g)
    (db,) = canvas.draw()

    assert db.valid
    assert rect_equal(g.bbox, db.db)
    assert rect_equal(db.db.figs[0], r)
    assert segment_equal(db.db.figs[1], s)


def test_create_nested_group(ws, canvas, cleanup):
    one = Rect[0:0.1, 0.2:0.3, Layer('M1', 'drawing')]
    two = one.copy()
    two.translate(left=one.right)
    group_one = Group([one, two])

    three = one.copy()
    three.translate(top=one.bottom)

    group_two = Group([group_one, three])

    canvas.append(group_two)
    (db,) = canvas.draw()

    assert rect_equal(group_two.bbox, db.db)
    assert rect_equal(db.db.figs[1], three)
    assert rect_equal(db.db.figs[0].figs[0], one)
    assert rect_equal(db.db.figs[0].figs[1], two)


def test_delete_works(ws, canvas, cleanup):
    one = Rect[0:0.1, 0.2:0.3, Layer('M1', 'drawing')]
    group = Group([one])

    canvas.append(group)
    (db,) = canvas.draw()

    rect_db = DbShape(db.db.figs[0])

    rect_db.delete()

    assert not db.db.figs
    assert not rect_db.valid
    assert db.valid


def test_align(ws, cv, cell_cv):
    """
    Crosses all alignable objects inheriting from
    figure with PR alignment for instances, align handles and maintain flag for the align method.
    """
    dummy_layer = Layer("M1", "drawing")

    @dataclass
    class Alignable:
        shape: Figure
        align_at: str
        rect: Rect

        @property
        def align(self):
            if self.align_at == "b_box":
                return self.shape.b_box
            elif self.align_at == "pr_boundary":
                return self.shape.pr_boundary

        @property
        def b_box(self) -> BoundingBox:
            if self.align_at == "b_box":
                return self.shape.skill_b_box
            elif self.align_at == "pr_boundary":
                return self.shape.skill_pr_boundary

    count = 0

    @contextmanager
    def create_inst():
        nonlocal count
        name = f"I{count}_test"
        db = ws.db.create_inst(cv, cell_cv, name, (0, 0), "R0")
        count += 1
        try:
            shape = Instance.from_name(cv, name)
            yield Alignable(shape=shape, align_at="b_box", rect=Rect[-1:11, -3:7])
        finally:
            ws.db.delete_object(db)

    @contextmanager
    def create_pr_inst():
        # Instance to be aligned at the P&R boundary
        with create_inst() as inst:
            yield Alignable(shape=inst.shape, align_at="pr_boundary", rect=Rect[-1:7, -3:5])

    @contextmanager
    def create_inst_group():
        with create_inst() as inst, create_inst() as ref_inst:
                shape = inst.shape.b_box.align(center_left=ref_inst.shape.b_box.center_right)
                b_box = shape.skill_b_box
                yield Alignable(
                    shape=shape,
                    align_at="b_box",
                    rect=Rect[b_box[0][0] : b_box[1][0], b_box[0][1] : b_box[1][1]],
                )

    @contextmanager
    def create_db_shape():
        canvas = Canvas(cv)
        rect = Rect[0:1, 3:7, dummy_layer]
        group = Group([rect])
        canvas.append(group)
        (db,) = canvas.draw()

        rect_db = DbShape(db.db)

        yield Alignable(shape=rect_db, align_at="b_box", rect=rect)
        rect_db.delete()

    @contextmanager
    def create_rod_shape():
        b_box = ((-3, -5), (13, 17))
        rod = ws.rod.create_rect(cv_id=cv, layer=dummy_layer, b_box=b_box)
        shape = RodShape.from_rod(cast(RemoteObject, rod))
        yield Alignable(
            shape=shape,
            align_at="b_box",
            rect=Rect[b_box[0][0] : b_box[1][0], b_box[0][1] : b_box[1][1]],
        )
        shape.delete()

    # Align for bounding box
    handles = python_skill_handle
    shapes = (create_inst, create_pr_inst, create_inst_group, create_db_shape, create_rod_shape)
    for maintain in (True, False):
        for handle1, handle2 in ((x, y) for x in handles for y in handles):
            for create_s1, create_s2 in ((x, y) for x in shapes for y in shapes):
                with create_s1() as s1, create_s2() as s2:
                    if maintain and (
                        create_s1 in (create_inst_group, create_pr_inst, create_db_shape)
                        or create_s2 in (create_inst_group, create_pr_inst, create_db_shape)
                    ):
                        with pytest.raises(ValueError):
                            s1.align.align(
                                **{handle1: getattr(s2.align, handle2)}, maintain=maintain
                            )
                    else:
                        s1.align.align(
                            **{handle1: getattr(s2.align, handle2)}, maintain=maintain
                        )
                        # Actual bounding box of moved s1
                        # (as Rect to simplify comparision with expected position)
                        new_rect = Rect[
                            s1.b_box[0][0] : s1.b_box[1][0], s1.b_box[0][1] : s1.b_box[1][1]
                        ]
                        assert getattr(new_rect, handle1) == getattr(s2.rect, handle2)
