import meerkat as mk
from app.src.lib.components import ExampleComponent

# Import and use the ExampleComponent
example_component = ExampleComponent(name="Meerkat")

# Launch the Meerkat GUI
# mk.gui.start() # not required for running with `mk run`
interface = mk.gui.Interface(component=example_component, id="example")
interface.launch()
