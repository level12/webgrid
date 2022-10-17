Types
=====

Types are defined for grid JSON input/output. These can be mirrored on the consumer
side for API integrity (e.g. in TypeScript).

Typically, in API usage, the consumer app will be building/maintaining a ``GridSettings``
object to send to the API, and accepting a ``Grid`` in response.

Settings Types
##############

.. autoclass:: webgrid.types.Filter
    :members:

.. autoclass:: webgrid.types.Paging
    :members:

.. autoclass:: webgrid.types.Sort
    :members:

.. autoclass:: webgrid.types.GridSettings
    :members:

Grid Types
##########

.. autoclass:: webgrid.types.ColumnGroup
    :members:

.. autoclass:: webgrid.types.FilterOperator
    :members:

.. autoclass:: webgrid.types.FilterOption
    :members:

.. autoclass:: webgrid.types.FilterSpec
    :members:

.. autoclass:: webgrid.types.GridSpec
    :members:

.. autoclass:: webgrid.types.GridState
    :members:

.. autoclass:: webgrid.types.Grid
    :members:
