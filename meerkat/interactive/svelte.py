import importlib.util
import logging
import os
import shutil
import sys
from typing import TYPE_CHECKING, List, Set, Type

from tabulate import tabulate

from meerkat.constants import (
    JINJA_ENV,
    MEERKAT_INIT_PROCESS,
    MEERKAT_NPM_PACKAGE,
    MEERKAT_RUN_ID,
    MEERKAT_RUN_PROCESS,
    MEERKAT_RUN_RELOAD_COUNT,
    MEERKAT_RUN_SUBPROCESS,
    App,
    PathHelper,
    write_file,
)
from meerkat.interactive import BaseComponent
from meerkat.tools.filelock import FileLock
from meerkat.tools.singleton import Singleton

if TYPE_CHECKING:
    from meerkat.interactive import Page

logger = logging.getLogger(__name__)


def get_subclasses_recursive(cls: type) -> List[type]:
    """Recursively find all subclasses of a class.

    Args:
        cls (type): the class to find subclasses of.

    Returns:
        List[type]: a list of all subclasses of cls.
    """
    subclasses = []
    for subclass in cls.__subclasses__():
        subclasses.append(subclass)
        subclasses.extend(get_subclasses_recursive(subclass))
    return subclasses


def write_file_if_changed(path: str, content: str):
    """Write a file if the content has changed. Note this is not atomic.

    Args:
        path (str): the path to write to.
        content (str): the content to write.
    """
    if os.path.exists(path):
        with open(path, "r") as f:
            if f.read() == content:
                return
    write_file(path, content)


class SvelteWriter(metaclass=Singleton):
    """Class that handles writing Svelte components to a Meerkat app."""

    def __init__(self):
        self.app = App(appdir=PathHelper().appdir)

        self._ran_import_app_components = False
        self._components = None
        self._frontend_components = None

    @property
    def appdir(self):
        return self.app.appdir

    def run(self):
        """Write component wrappers and context at the start of a run."""
        self.import_app_components()
        with FileLock(os.path.join(self.appdir, "svelte_writer")):
            self.cleanup()
            self.write_all_component_wrappers()  # src/lib/wrappers/
            self.write_component_context()  # ComponentContext.svelte

    def cleanup(self):
        """Cleanup the app."""
        self.remove_all_component_wrappers()
        self.remove_component_context()
        logger.debug("Removed all component wrappers and ComponentContext.svelte.")

    def get_all_components(
        self,
        exclude_classes: Set[str] = {"Component", "BaseComponent"},
    ) -> List[Type["BaseComponent"]]:
        """Get all subclasses of BaseComponent, excluding the ones in
        `exclude_classes`.

        Args:
            exclude_classes (Set[str], optional): Set of classes
                to exclude. Defaults to {"Component", "BaseComponent"}.

        Returns:
            List[Type["BaseComponent"]]: List of subclasses of BaseComponent.
        """
        if self._components:
            return self._components

        # Recursively find all subclasses of Component
        subclasses = get_subclasses_recursive(BaseComponent)

        # Filter out the classes we don't want and sort
        subclasses = [c for c in subclasses if c.__name__ not in exclude_classes]
        subclasses = sorted(subclasses, key=lambda c: c.alias)

        tabulated_subclasses = tabulate(
            [[subclass.__module__, subclass.__name__] for subclass in subclasses]
        )
        logger.debug(f"Found {len(subclasses)} components.\n" f"{tabulated_subclasses}")

        self._components = subclasses
        return subclasses

    def get_all_frontend_components(self) -> List[Type["BaseComponent"]]:
        """Get all subclasses of BaseComponent that have a unique
        frontend_alias.

        Returns:
            List[Type["BaseComponent"]]: List of subclasses of BaseComponent.
        """
        if self._frontend_components:
            return self._frontend_components

        # Create a `frontend_components` list that contains the
        # components that have unique component.frontend_alias
        components = self.get_all_components()
        frontend_components = []
        aliases = set()
        for component in components:
            if component.frontend_alias not in aliases:
                frontend_components.append(component)
                aliases.add(component.frontend_alias)

        self._frontend_components = frontend_components
        return frontend_components

    def import_app_components(self):
        """Import all components inside the app/src/lib/components directory to
        register custom user components from their app."""
        if self._ran_import_app_components:
            # Only run this once in a process
            return

        if self.app.is_user_app:
            # Import all components inside the app/src/lib/components
            # directory to register user components from the app
            # Otherwise do nothing
            logger.debug(
                "The app being run is as a user app. "
                f"Adding {self.appdir} to sys.path. "
                "Importing app components from app/src/lib/components."
            )

            # StackOverflow:
            # How can I import a module dynamically given the full path?
            # https://stackoverflow.com/a/67692
            # This module name can be anything
            module_name = "user.app.src.lib.components"
            spec = importlib.util.spec_from_file_location(
                module_name,
                f"{self.appdir}/src/lib/components/__init__.py",
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

        self._ran_import_app_components = True

    def remove_all_component_wrappers(self):
        """Remove all component wrappers from the app."""
        try:
            shutil.rmtree(f"{self.appdir}/src/lib/wrappers")
        except (FileNotFoundError, OSError):
            pass

    def remove_component_context(self):
        """Remove the ComponentContext.svelte file from the app."""
        try:
            os.remove(f"{self.appdir}/src/lib/ComponentContext.svelte")
        except OSError:
            pass

    def render_component_context(self):
        """Render the ComponentContext.svelte file for the app."""
        template = JINJA_ENV.get_template("ComponentContext.svelte")
        components = self.get_all_components()
        frontend_components = self.get_all_frontend_components()

        # Get the libraries that the frontend components
        # depend on
        libraries = set([c.library for c in frontend_components])

        # Filter to only include components and frontend components
        # whose libraries are installed
        installed_libraries = self.app.filter_installed_libraries(libraries) + ["html"]
        components = [
            c
            for c in components
            if c.library in installed_libraries
            or c.library == MEERKAT_NPM_PACKAGE
            and not self.app.is_user_app
        ]
        frontend_components = [
            c
            for c in frontend_components
            if c.library in installed_libraries
            or c.library == MEERKAT_NPM_PACKAGE
            and not self.app.is_user_app
        ]

        # For the Meerkat npm package, check the components offered by the
        # user's installed version, and filter out the ones that aren't available
        if MEERKAT_NPM_PACKAGE in installed_libraries and self.app.is_user_app:
            try:
                mk_components = set(
                    [f"Meerkat{c}" for c in self.app.get_mk_package_info()]
                )
                components = [
                    c
                    for c in components
                    if (c.frontend_alias in mk_components and c.namespace == "meerkat")
                    or (c.library == MEERKAT_NPM_PACKAGE and c.namespace != "meerkat")
                    or c.library != MEERKAT_NPM_PACKAGE
                ]
                frontend_components = [
                    c
                    for c in frontend_components
                    if (c.frontend_alias in mk_components and c.namespace == "meerkat")
                    or (c.library == MEERKAT_NPM_PACKAGE and c.namespace != "meerkat")
                    or c.library != MEERKAT_NPM_PACKAGE
                ]
            except Exception as e:
                logger.error(
                    "Error getting Meerkat package info. "
                    "Components from the Meerkat npm package may not be available."
                )
                logger.debug(e)

        return template.render(
            components=components,
            frontend_components=frontend_components,
        )

    def render_component_wrapper(self, component: Type[BaseComponent]):
        # TODO: fix line breaks in Wrapper.svelte
        template = JINJA_ENV.get_template("Wrapper.svelte")
        from meerkat.interactive.startup import snake_case_to_camel_case

        prop_names_camel_case = [
            snake_case_to_camel_case(prop_name) for prop_name in component.prop_names()
        ]
        
        print(component)

        return template.render(
            import_style=component.wrapper_import_style,
            component_name=component.component_name,
            path=component.path,
            prop_names=component.prop_names(),
            prop_names_camel_case=prop_names_camel_case,
            event_names=component.event_names(),
            use_bindings=True,
            prop_bindings=component.prop_bindings(),
            slottable=component.slottable,
            zip=zip,
            is_user_app=self.app.is_user_app,
        )

    def get_import_prefix(self):
        if self.app.is_user_app:
            # Use the MEERKAT_NPM_PACKAGE package instead of $lib
            # in a Meerkat generated app
            return MEERKAT_NPM_PACKAGE
        return "$lib"

    def render_route(self, page: "Page"):
        template = JINJA_ENV.get_template("page.svelte.jinja")

        # TODO: make this similar to render_root_route
        #       and use component.frontend_alias and component.alias
        return template.render(
            route=page.id,
            title=page.name,
            import_prefix=self.get_import_prefix(),
            components=list(sorted(page.component.get_components())),
            queryparam=False,
        )

    def render_root_route(self):
        template = JINJA_ENV.get_template("page.root.svelte.jinja")
        components = self.get_all_components()
        frontend_components = self.get_all_frontend_components()

        return template.render(
            title="Meerkat",
            import_prefix=self.get_import_prefix(),
            components=components,
            frontend_components=frontend_components,
        )

    def write_component_wrapper(self, component: Type[BaseComponent]):
        cwd = f"{self.appdir}/src/lib/wrappers/__{component.namespace}"
        os.makedirs(cwd, exist_ok=True)
        write_file_if_changed(
            f"{cwd}/{component.__name__}.svelte",
            self.render_component_wrapper(component),
        )

    def write_all_component_wrappers(
        self,
        exclude_classes: Set[str] = {"Component", "BaseComponent"},
    ):
        # Recursively find all subclasses of BaseComponent
        subclasses = get_subclasses_recursive(BaseComponent)
        for subclass in subclasses:
            # Use subclass.__name__ as the component name, instead of
            # subclass.component_name, because the latter is not guaranteed to be
            # unique.
            component_name = subclass.__name__
            if component_name in exclude_classes:
                continue

            # Make a file for the component, inside a subdirectory for the namespace
            # e.g. src/lib/wrappers/__meerkat/Component.svelte
            self.write_component_wrapper(subclass)

    def write_component_context(self):
        write_file_if_changed(
            f"{self.appdir}/src/lib/ComponentContext.svelte",
            self.render_component_context(),
        )


"""
Convert all Python component classes to Svelte component wrappers.

We only run the following code if
  - a script importing `meerkat` is run directly with Python e.g. `python myscript.py`
  - a notebook importing `meerkat` is run directly with Jupyter
  - a script was run with `mk run` and we are in the `mk run` process
  - a script was run with `mk run`, we are in its `uvicorn` subprocess
    and this is a live reload run (i.e. not the first run of the subprocess)
"""
if (
    (not MEERKAT_RUN_PROCESS and not MEERKAT_RUN_SUBPROCESS)
    or MEERKAT_RUN_PROCESS
    or (MEERKAT_RUN_SUBPROCESS and MEERKAT_RUN_RELOAD_COUNT > 1)
) and not MEERKAT_INIT_PROCESS:
    logger.debug("Running SvelteWriter().run().")
    SvelteWriter().run()

if MEERKAT_RUN_SUBPROCESS:
    # Increment the MEERKAT_RUN_RELOAD_COUNT
    # so that the `uvicorn` subprocess knows that it has been reloaded
    # on a subsequent live reload run
    write_file(
        f"{PathHelper().appdir}/.{MEERKAT_RUN_ID}.reload",
        str(MEERKAT_RUN_RELOAD_COUNT + 1),
    )
