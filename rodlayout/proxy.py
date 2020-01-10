import operator
from contextlib import contextmanager
from typing import Generator, cast, List, Iterable
from dataclasses import dataclass

from geometry.point import TuplePoint
from skillbridge import current_workspace
from skillbridge.client.hints import SkillTuple
from skillbridge.client.objects import RemoteObject

from geometry import Point

from rodlayout.hints import BoundingBox
from .handle import python_skill_handle
from .transform import Transform

TupleVector = TuplePoint


@dataclass(frozen=True)
class _AlignHandle:
    _shape: 'Figure'
    _pr: bool
    _handle: str

    def __getattr__(self, handle: str) -> '_AlignHandle':
        return _AlignHandle(self._shape, self._pr, python_skill_handle[handle])

    def align(
        self, sep: TupleVector = (0, 0), maintain: bool = False, **handle: '_AlignHandle'
    ) -> 'FigureCollection':
        assert len(handle) == 1, "Exactly 1 align handle expected."
        key, ref = handle.popitem()
        assert ref._handle, "Need a handle name for the reference object."
        try:
            align_handle = python_skill_handle[key]
        except KeyError:
            raise ValueError(f"There is no handle named {key!r}.") from None
        return self._do_align(align_handle=align_handle, ref=ref, sep=sep, maintain=maintain)

    def _do_align(
        self, align_handle: str, ref: '_AlignHandle', sep: TupleVector, maintain: bool
    ) -> 'FigureCollection':
        if maintain:
            raise ValueError("Cannot maintain alignment when figure has no rod representation.")
        cell_view = self._shape.cell_view
        with ghost_shape(cell_view, self._shape, self._pr) as align_rod:
            with ghost_shape(cell_view, ref._shape, ref._pr) as ref_rod:
                current_workspace.rod.align(
                    align_obj=align_rod,
                    align_handle=align_handle,
                    ref_obj=ref_rod,
                    ref_handle=ref._handle,
                    maintain=False,
                    x_sep=sep[0],
                    y_sep=sep[1],
                )
        return FigureCollection([self._shape, ref._shape], cell_view)


@dataclass(frozen=True)
class _RodAlignHandle(_AlignHandle):
    def _do_align(
        self, align_handle: str, ref: '_AlignHandle', sep: TupleVector, maintain: bool
    ) -> 'FigureCollection':
        if maintain and not isinstance(ref._shape, RodShape):
            raise ValueError(
                "Cannot maintain alignment when ref objects has no rod representation."
            )
        if maintain and (self._pr or ref._pr):
            raise ValueError("Cannot maintain alignment for pr boundary.")

        if (
            not isinstance(ref._shape, RodShape)
            or not isinstance(self._shape, RodShape)
            or self._pr
            or ref._pr
        ):
            return super()._do_align(align_handle, ref, sep, maintain)

        current_workspace.rod.align(
            align_obj=self._shape.rod,
            align_handle=align_handle,
            ref_obj=ref._shape.rod,
            ref_handle=ref._handle,
            maintain=maintain,
            x_sep=sep[0],
            y_sep=sep[1],
        )
        return FigureCollection([self._shape, ref._shape], self._shape.cell_view)


class Figure:
    """
    A proxy to an existing figure in virtuoso
    or a wrapper for concepts not supported natively.
    E.g. a loose collection of figures.
    """

    @property
    def cell_view(self) -> RemoteObject:
        """
        Each figure exists in one specific cell view.
        :return: Cell view of this figure.
        """
        raise NotImplementedError

    def __getattr__(self, handle: str) -> _AlignHandle:
        return _AlignHandle(self, False, python_skill_handle[handle])

    @property
    def b_box(self) -> _AlignHandle:
        return _AlignHandle(self, False, '')

    @property
    def skill_b_box(self) -> BoundingBox:
        """
        :return: Bounding box for this figure.
        """
        raise NotImplementedError

    @property
    def skill_pr_boundary(self) -> BoundingBox:
        """

        """
        raise NotImplementedError

    def get_db_ids(self) -> Iterable[RemoteObject]:
        """
        :return: Flat list of all database instance ids contained in this figure.
        """
        raise NotImplementedError


@dataclass(frozen=True)
class FigureCollection(Figure):
    """
    Represents a collection of figures in Virtuoso.

    This class has no direct representation in Virtuoso and can thus not be identified by a single
    database id and the like.

    The purpose of ``FigureCollection`` is to allow an align on multiple objects,
    which is not natively supported by skill.
    """

    @property
    def skill_pr_boundary(self) -> BoundingBox:
        raise NotImplementedError("Figure collection does not have a pr boundary.")

    elements: List[Figure]
    _cell_view: RemoteObject

    @property
    def cell_view(self) -> RemoteObject:
        return self._cell_view

    @property
    def skill_b_box(self) -> BoundingBox:
        """
        :return: Bounding box drawn by all instances contained in this group.
                 Determined by b_box value of figure group.
        """
        group_id = current_workspace.db.create_fig_group(
            self.cell_view, None, False, cast(SkillTuple, (0, 0)), Transform.identity.value,
        )
        for inst_id in self.get_db_ids():
            current_workspace.db.add_fig_to_fig_group(group_id, inst_id)
        b_box = cast(RemoteObject, group_id).b_box
        current_workspace.db.delete_object(group_id)
        return cast(BoundingBox, b_box)

    def get_db_ids(self) -> Generator[RemoteObject, None, None]:
        """
        :return: All database ids contained in ``elements``.
        """
        for element in self.elements:
            yield from element.get_db_ids()


@dataclass(frozen=True)
class DbShape(Figure):
    """
    A proxy to an existing shape in Virtuoso.

    The shape only consists of a db object without a rod object.
    E.g. figure groups will be represented as a ``DbShape``
    """

    db: RemoteObject

    @property
    def skill_b_box(self) -> BoundingBox:
        return cast(BoundingBox, self.db.b_box)

    @property
    def skill_pr_boundary(self) -> BoundingBox:
        raise NotImplementedError("Db Shape does not have a pr boundary.")

    @property
    def cell_view(self) -> RemoteObject:
        return cast(RemoteObject, self.db.cell_view)

    def __str__(self) -> str:
        return f"{self.db.obj_type}@{self.db.skill_id}"

    def __repr__(self) -> str:
        return self.__str__()

    def delete(self, children: bool = True, redraw: bool = False) -> None:
        """
        Delete the db object.

        Setting ``children`` to ``True`` will also delete the child shapes if this
        is a figure group.

        Setting ``redraw`` to ``True`` will refresh the view in Virtuoso

        .. warning ::

            After you deleted an object you should discard the python variable, too,
            because the underlying db object is not valid anymore.

        """
        if children:
            for fig in self.db.figs or ():
                DbShape(fig).delete(children=True, redraw=False)
        current_workspace.db.delete_object(self.db)
        if redraw:
            current_workspace.hi.redraw()

    @property
    def valid(self) -> bool:
        """
        Check if the db object is still valid and was not deleted.
        """
        return cast(bool, current_workspace.db.valid_p(self.db))

    def _copy_figure(
        self, cell_view: RemoteObject, translate: Point, transform: Transform
    ) -> RemoteObject:
        translate_transform = cast(SkillTuple, (translate, transform))
        db = current_workspace.db.copy_fig(self.db, cell_view, translate_transform)

        return cast(RemoteObject, db)

    def copy(
        self, translate: Point = Point(0, 0), transform: Transform = Transform.identity
    ) -> 'DbShape':
        """
        Copy the dbShape and translate, transform the copy.
        """
        return DbShape(self._copy_figure(self.db.cell_view, translate, transform))

    def children(self) -> Generator['RodShape', None, None]:
        """
        Get all RodShapes within a Group and its hierarchy
        """
        for fig in self.db.figs:
            if fig.obj_type == 'figGroup':
                yield from DbShape(fig).children()
            else:
                rod = current_workspace.rod.get_obj(fig)
                yield RodShape.from_rod(cast(RemoteObject, rod))

    def get_db_ids(self) -> List[RemoteObject]:
        """
        :return: Database id for this shape.
        """
        return [self.db]


@dataclass(frozen=True)
class RodShape(DbShape):
    """
    A proxy to an existing shape in Virtuoso with a rod object.

    This proxy also contains the rod object which allows aligning and other features.
    E.g. rectangles and paths will be represented as a ``RodShape``
    """

    # db: RemoteObject
    rod: RemoteObject

    def __getattr__(self, handle: str) -> _RodAlignHandle:
        return _RodAlignHandle(self, False, python_skill_handle[handle])

    @property
    def skill_pr_boundary(self) -> BoundingBox:
        raise NotImplementedError("Rod Shape has no pr boundary.")

    @property
    def b_box(self) -> _RodAlignHandle:
        return _RodAlignHandle(self, False, '')

    @classmethod
    def from_rod(cls, rod: RemoteObject) -> 'RodShape':
        """
        Create a rod proxy from an existing rod object in virtuoso.
        """
        return RodShape(rod.db_id, rod)

    def copy(
        self, translate: Point = Point(0, 0), transform: Transform = Transform.identity
    ) -> 'RodShape':
        """
        Copy the RodShape and translate, transform the copy.
        """
        db = self._copy_figure(self.rod.cv_id, translate, transform)
        rod = current_workspace.rod.name_shape(shape_id=db)

        return RodShape(db, cast(RemoteObject, rod))


@dataclass(frozen=True)
class Instance(RodShape):
    """
    A proxy to an existing instance.
    """

    @classmethod
    def from_name(cls, cell_view: RemoteObject, name: str) -> 'Instance':
        db = cast(RemoteObject, current_workspace.db.find_any_inst_by_name(cell_view, name))
        assert db is not None
        rod = cast(RemoteObject, current_workspace.rod.get_obj(db))
        assert rod is not None

        return Instance(db, rod)

    @property
    def pr_boundary(self) -> _AlignHandle:
        return _AlignHandle(self, True, '')

    @property
    def skill_pr_boundary(self) -> BoundingBox:
        cv_rel_pr_box = self.db.master.pr_boundary.b_box

        inst_rel_pr_box = [
            list(map(operator.sub, p, self.db.master.b_box[0])) for p in cv_rel_pr_box
        ]
        abs_pr_box = [list(map(operator.add, p, self.db.b_box[0])) for p in inst_rel_pr_box]

        return cast(BoundingBox, abs_pr_box)

    def get_db_ids(self) -> List[RemoteObject]:
        return [self.db]


@contextmanager
def ghost_shape(
    cell_view: RemoteObject, figure: Figure, pr: bool
) -> Generator[RemoteObject, None, None]:
    """
    Allows for any ``Figure`` to be handled like a rod object.
    All instances are grouped along with a new rod shape, specified by the figure bounding box.
    The figure may than be aligned on this rod shape.
    """
    b_box = figure.skill_pr_boundary if pr else figure.skill_b_box
    rod_shape = cast(
        RemoteObject,
        current_workspace.rod.create_rect(
            layer="M1", cv_id=cell_view, b_box=cast(SkillTuple, b_box)
        ),
    )
    group_id = current_workspace.db.create_fig_group(
        cell_view, None, False, cast(SkillTuple, (0, 0)), Transform.identity.value
    )
    current_workspace.db.add_fig_to_fig_group(group_id, rod_shape.db_id)
    for inst_id in figure.get_db_ids():
        current_workspace.db.add_fig_to_fig_group(group_id, inst_id)

    try:
        yield rod_shape

    finally:
        current_workspace.db.delete_object(group_id)
        current_workspace.db.delete_object(rod_shape.db_id)
