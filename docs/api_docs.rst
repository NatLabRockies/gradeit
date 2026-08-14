API Reference
=============

Everything below is re-exported from the top-level ``gradeit`` package, so
``from gradeit import gradeit, USGSLocal, Wood2014Filter`` is the expected import
style. The submodules are documented directly to keep each entry in one place.

Core
----

.. automodule:: gradeit.core
   :members: gradeit

.. automodule:: gradeit.io
   :members: GradeResult, to_coordinates

.. automodule:: gradeit.coordinate
   :members:

.. automodule:: gradeit.grade
   :members: get_grade, get_distances, haversine

Elevation models
----------------

.. automodule:: gradeit.elevation.elevation_model
   :members:

.. automodule:: gradeit.elevation.usgs_api
   :members: USGSApi

.. automodule:: gradeit.elevation.usgs_local
   :members: USGSLocal, get_raster_elev_profile, build_grid_refs

Filters
-------

.. automodule:: gradeit.filters.elevation_filter
   :members:

.. automodule:: gradeit.filters.wood2014
   :members: Wood2014Filter, resolve_parameters, binomial_kernel, binomial_filter

.. automodule:: gradeit.filters.bridge
   :members: BridgeFilter

.. automodule:: gradeit.filters.savitzky_golay
   :members: SavitzkyGolayFilter, savgol_filter

Plotting
--------

.. automodule:: gradeit.plotting
   :members: plot_grade_map

Exceptions
----------

.. automodule:: gradeit.exceptions
   :members:
   :show-inheritance:
