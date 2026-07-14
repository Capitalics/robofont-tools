try:
    import booleanOperations  # noqa: F401
    import shapely  # noqa: F401
except ImportError:
    from mojo.pipTools import installNeededPackages
    from vanilla.dialogs import message

    installNeededPackages(
        "Fracturize",
        [
            {
                "packageName": "booleanOperations>=0.10,<1",
                "importName": "booleanOperations",
            },
            {"packageName": "shapely>=2.1,<3", "importName": "shapely"},
        ],
    )
    message(
        "Fracturize dependency required",
        "Fracturize's geometry dependencies will be installed into RoboFont's external packages. Restart RoboFont, then choose Extensions > Fracturize again.",
    )
else:
    from fracturize.extension import open_window

    open_window()
