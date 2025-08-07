# --------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# --------------------------------------------------------------------

import glob
import importlib.util
import json
import logging
import pathlib
import sys
from itertools import chain
from types import ModuleType
from typing import TYPE_CHECKING

from invesalius import inv_paths
from invesalius.pubsub import pub as Publisher

if TYPE_CHECKING:
    import os

# Setup logger for the plugin manager
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


def import_source(module_name: str, module_file_path: "str | bytes | os.PathLike") -> ModuleType:
    module_spec = importlib.util.spec_from_file_location(module_name, module_file_path)
    if module_spec is None:
        raise ImportError(f"No module named {module_name}")
    module = importlib.util.module_from_spec(module_spec)
    if module_spec.loader is None:
        raise ImportError(f"Loader is None for module {module_name}")
    module_spec.loader.exec_module(module)
    return module


class PluginManager:
    def __init__(self):
        self.plugins = {}
        self.__bind_pubsub_evt()

    def __bind_pubsub_evt(self) -> None:
        Publisher.subscribe(self.load_plugin, "Load plugin")

    def find_plugins(self) -> None:
        self.plugins = {}
        plugin_json_paths = chain(
            glob.glob(str(inv_paths.PLUGIN_DIRECTORY.joinpath("**/plugin.json")), recursive=True),
            glob.glob(str(inv_paths.USER_PLUGINS_DIRECTORY.joinpath("**/plugin.json")), recursive=True),
        )

        for plugin_path_str in plugin_json_paths:
            plugin_path = pathlib.Path(plugin_path_str)

            try:
                with plugin_path.open(encoding="utf-8") as f:
                    jdict = json.load(f)

                plugin_name = jdict["name"]
                plugin_description = jdict["description"]
                enable_startup = jdict.get("enable-startup", False)

                self.plugins[plugin_name] = {
                    "name": plugin_name,
                    "description": plugin_description,
                    "folder": plugin_path.parent,
                    "enable_startup": enable_startup,
                }

            except FileNotFoundError:
                logger.warning(f"Plugin file not found: {plugin_path}")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON for plugin at {plugin_path}: {e}")
            except KeyError as e:
                logger.warning(f"Missing required key in plugin.json ({plugin_path}): {e}")
            except Exception as e:
                logger.error(f"Unexpected error loading plugin at {plugin_path}: {e}", exc_info=True)

        Publisher.sendMessage("Add plugins menu items", items=self.plugins)

    def load_plugin(self, plugin_name: str) -> None:
        if plugin_name in self.plugins:
            try:
                plugin_module = import_source(
                    plugin_name, self.plugins[plugin_name]["folder"].joinpath("__init__.py")
                )
                sys.modules[plugin_name] = plugin_module
                main = importlib.import_module(plugin_name + ".main")
                main.load()
            except FileNotFoundError as e:
                logger.error(f"Plugin file missing for {plugin_name}: {e}")
            except ModuleNotFoundError as e:
                logger.error(f"Main module missing in plugin {plugin_name}: {e}")
            except Exception as e:
                logger.exception(f"Unexpected error while loading plugin '{plugin_name}': {e}")
