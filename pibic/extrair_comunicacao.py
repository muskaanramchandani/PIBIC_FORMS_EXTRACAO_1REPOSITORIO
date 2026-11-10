#!/usr/bin/env python3
"""
Micro frontends e comunicação entre eles, por análise estática.

Para cada sistema (uma pasta com um ou mais repositórios), extrai:

1. os micro frontends: quantos e quais;
2. os tipos de comunicação usados entre eles, incluindo o estado
   global (armazenamento do navegador e bibliotecas de estado).

É um recorte independente das regras do DAMFE, só com essas duas
extrações, lendo o código com tree-sitter. Não importa nada do DAMFE.

Uso:
    python3 extrair_comunicacao.py <sistema> [<sistema> ...] [--saida DIR]
    python3 extrair_comunicacao.py --pasta <pasta com um sistema por subpasta> [--saida DIR]

Com --saida, grava em DIR:
    sistemas.csv      uma linha por sistema: nº de MFEs e tipos de comunicação entre eles
    comunicacao.csv   uma linha por sistema e mecanismo
    <sistema>.json    MFEs, ligações e cada ocorrência com arquivo e linha

Dependências (a mesma faixa do DAMFE; misturar versões quebra a ABI):
    pip install "tree-sitter>=0.23,<0.24" "tree-sitter-javascript>=0.23,<0.24" \
                "tree-sitter-typescript>=0.23,<0.24"

Como os MFEs são encontrados:
- single-spa: `registerApplication` (forma de objeto e posicional),
  `<application name>` do single-spa-layout, e pacote cujo módulo
  exporta `bootstrap`, `mount` e `unmount`. O orquestrador (quem
  chama `registerApplication`) conta como MFE, como no DAMFE;
- Module Federation: `ModuleFederationPlugin`, `withModuleFederation`,
  `federation` (Vite) e afins com `name`, nos arquivos de build.
A mesma unidade achada por dois caminhos conta uma vez (pelo diretório).
O total conta as unidades com código no sistema e as registradas por
`registerApplication` mesmo sem o código, como o DAMFE; o nome que só
aparece no layout, sem código, fica de fora. Os registrados sem código
são listados em `sem_codigo`.

Mecanismos de comunicação (mensagem):
    CustomEvent       dispatchEvent(new CustomEvent(c)) e addEventListener(c) em window/document,
                      fromEvent(window, c)
    postMessage       janela.postMessage({type: c}, origem) e o listener de "message"
    BroadcastChannel  new BroadcastChannel(c), postMessage e onmessage
    rxjs-subject      x.next()/x.subscribe() sobre um objeto importado de outro módulo
    mitt, eventemitter3, tiny-emitter, pubsub-js   emit/on, publish/subscribe
    customProps       customProps do registerApplication (orquestrador -> MFE)
Estado global:
    localStorage, sessionStorage   getItem, setItem, removeItem, clear (também por função que repassa a chave)
    redux             useSelector (e apelidos, como useAppSelector); store criado no próprio MFE não conta
    zustand, jotai, recoil, pinia  o hook ou átomo usado

Um canal liga dois MFEs quando um produz e outro consome o mesmo canal
(mensagem) ou quando dois tocam a mesma chave ou fatia (estado). Código
de pacote compartilhado que não é MFE conta para cada MFE que o importa.

Simplificações em relação ao DAMFE: não descarta código morto, não
resolve import map nem tsconfig `paths`, e segue constantes só pelo
próprio arquivo e pelos imports relativos ou de pacote do repositório.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
from tree_sitter import Language, Node, Parser


# ----------------------------------------------------------------------
# Catálogos
# ----------------------------------------------------------------------

JS = Language(tsjs.language())
TS = Language(tsts.language_typescript())
TSX = Language(tsts.language_tsx())

LANGUAGES = {".js": JS, ".jsx": JS, ".mjs": JS, ".cjs": JS, ".ts": TS, ".tsx": TSX}

EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")

IGNORED_DIRECTORIES = {
    "node_modules", "dist", "build", ".git", ".next", "coverage", "__pycache__",
    "__tests__", "__mocks__", "cypress", "e2e",
}

#: `x.spec.ts`, `x.test.js`
TEST_MARKERS = ("spec", "test")

LIFECYCLES = {"bootstrap", "mount", "unmount"}

FEDERATION_CALLS = {
    "ModuleFederationPlugin", "withModuleFederation", "NxModuleFederationPlugin",
    "federation", "moduleFederationPlugin",
}

FEDERATION_CONFIGS = (
    "webpack.config", "webpack.prod", "webpack.dev", "vite.config", "rspack.config",
    "module-federation.config", "federation.config", "next.config",
)

#: Eventos do próprio navegador: listener neles não é canal entre MFEs.
NATIVE_EVENTS = {
    "click", "change", "input", "submit", "focus", "blur", "keydown", "keyup",
    "keypress", "mousedown", "mouseup", "mousemove", "mouseover", "mouseout",
    "scroll", "resize", "load", "unload", "beforeunload", "DOMContentLoaded",
    "popstate", "hashchange", "storage", "message", "error", "touchstart",
    "touchend", "touchmove", "visibilitychange",
}

GLOBAL_TARGETS = {"window", "document", "globalThis", "self", "window.document"}

#: Campos do payload que fazem de canal em `postMessage({type: ...}, origem)`.
MESSAGE_TYPE_FIELDS = ("type", "action", "event", "name")

STORAGES = {"localStorage", "sessionStorage"}

STORAGE_ACCESS = {"getItem": "lê", "setItem": "escreve", "removeItem": "escreve", "clear": "escreve"}

ALL_KEYS = "*"

PARAM = "{param}"

RX_INTERNAL = ("rxjs", "rxjs/operators")

#: Barramentos: módulo -> (verbos que produzem, verbos que consomem)
BUSES = {
    "mitt": (("emit",), ("on",)),
    "eventemitter3": (("emit",), ("on", "once", "addListener")),
    "tiny-emitter": (("emit",), ("on", "once")),
    "pubsub-js": (("publish", "publishSync"), ("subscribe",)),
}

#: O que vem de cada biblioteca, pelo nome importado.
LIBRARY_ROLES = {
    ("react-redux", "useSelector"): ("selector",),
    ("redux", "createStore"): ("store-factory",),
    ("redux", "legacy_createStore"): ("store-factory",),
    ("@reduxjs/toolkit", "configureStore"): ("store-factory",),
    ("@reduxjs/toolkit", "createStore"): ("store-factory",),
    ("zustand", "create"): ("zustand-create",),
    ("zustand", "default"): ("zustand-create",),
    ("pinia", "defineStore"): ("pinia-define",),
    ("jotai", "useAtom"): ("atom-hook", "jotai", "lê"),
    ("jotai", "useAtomValue"): ("atom-hook", "jotai", "lê"),
    ("jotai", "useSetAtom"): ("atom-hook", "jotai", "escreve"),
    ("recoil", "useRecoilValue"): ("atom-hook", "recoil", "lê"),
    ("recoil", "useRecoilState"): ("atom-hook", "recoil", "lê"),
    ("recoil", "useSetRecoilState"): ("atom-hook", "recoil", "escreve"),
    ("mitt", "default"): ("bus-factory", "mitt"),
    ("mitt", "mitt"): ("bus-factory", "mitt"),
    ("eventemitter3", "default"): ("bus-class", "eventemitter3"),
    ("eventemitter3", "EventEmitter"): ("bus-class", "eventemitter3"),
    ("tiny-emitter", "default"): ("bus-class", "tiny-emitter"),
    ("pubsub-js", "default"): ("bus", "pubsub-js"),
    ("pubsub-js", "*"): ("bus", "pubsub-js"),
}

MESSAGE = "mensagem"
STATE = "estado global"

MECHANISMS = {
    "CustomEvent": MESSAGE, "postMessage": MESSAGE, "BroadcastChannel": MESSAGE,
    "rxjs-subject": MESSAGE, "mitt": MESSAGE, "eventemitter3": MESSAGE,
    "tiny-emitter": MESSAGE, "pubsub-js": MESSAGE, "customProps": MESSAGE,
    "localStorage": STATE, "sessionStorage": STATE, "redux": STATE,
    "zustand": STATE, "jotai": STATE, "recoil": STATE, "pinia": STATE,
}

SHARED = "(compartilhado)"


# ----------------------------------------------------------------------
# Árvore sintática
# ----------------------------------------------------------------------


def text(node: Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def walk(node: Node):
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def arguments_of(call: Node) -> list[Node]:
    arguments = call.child_by_field_name("arguments")
    if arguments is None:
        return []
    return [child for child in arguments.named_children if child.type != "comment"]


def callee(call: Node) -> Node | None:
    return call.child_by_field_name("function") or call.child_by_field_name("constructor")


def last_name(node: Node, source: bytes) -> str:
    return text(node, source).rpartition(".")[2].strip()


def string_of(node: Node, source: bytes) -> str | None:
    """O conteúdo de um literal de texto, ou de template sem substituição."""

    if node.type == "string":
        return "".join(text(child, source) for child in node.named_children if child.type in ("string_fragment", "escape_sequence"))
    if node.type == "template_string" and not any(child.type == "template_substitution" for child in node.named_children):
        return "".join(text(child, source) for child in node.named_children if child.type in ("string_fragment", "escape_sequence"))
    return None


def unwrap(node: Node) -> Node:
    """Tira parênteses, `as`, `!` e `satisfies` de volta do valor."""

    while node is not None and node.type in (
        "parenthesized_expression", "as_expression", "non_null_expression",
        "satisfies_expression", "type_assertion",
    ):
        inner = [child for child in node.named_children if not child.type.endswith("type") and child.type != "type_arguments"]
        if not inner:
            break
        node = inner[0]
    return node


def property_key(pair: Node, source: bytes) -> str | None:
    key = pair.child_by_field_name("key")
    if key is None:
        return None
    return string_of(key, source) if key.type == "string" else text(key, source)


def object_keys(node: Node, source: bytes) -> list[str]:
    keys = []
    for child in node.named_children:
        if child.type == "pair":
            name = property_key(child, source)
            if name:
                keys.append(name)
        elif child.type == "shorthand_property_identifier":
            keys.append(text(child, source))
        elif child.type == "method_definition":
            name = child.child_by_field_name("name")
            if name:
                keys.append(text(name, source))
    return keys


def object_property(node: Node, name: str, source: bytes) -> Node | None:
    for child in node.named_children:
        if child.type == "pair" and property_key(child, source) == name:
            return unwrap(child.child_by_field_name("value"))
        if child.type == "shorthand_property_identifier" and text(child, source) == name:
            return child
    return None


def is_function(node: Node | None) -> bool:
    return node is not None and node.type in (
        "arrow_function", "function_expression", "function", "function_declaration",
        "generator_function_declaration", "method_definition",
    )


def parameters_of(function: Node, source: bytes) -> list[str]:
    single = function.child_by_field_name("parameter")
    if single is not None:
        return [text(single, source)]
    parameters = function.child_by_field_name("parameters")
    if parameters is None:
        return []
    names = []
    for child in parameters.named_children:
        pattern = child.child_by_field_name("pattern") if child.type in ("required_parameter", "optional_parameter") else child
        if pattern is not None and pattern.type == "assignment_pattern":
            pattern = pattern.child_by_field_name("left")
        names.append(text(pattern, source) if pattern is not None and pattern.type == "identifier" else "")
    return names


# ----------------------------------------------------------------------
# Repositório
# ----------------------------------------------------------------------


def is_test(path: Path) -> bool:
    parts = path.name.split(".")
    return len(parts) > 2 and any(part in TEST_MARKERS for part in parts[1:-1])


def source_files(root: Path):
    for directory, children, files in os.walk(root):
        children[:] = sorted(child for child in children if child not in IGNORED_DIRECTORIES)
        for name in sorted(files):
            path = Path(directory) / name
            if path.suffix in LANGUAGES and not name.endswith(".d.ts") and not is_test(path):
                yield path


def layout_files(root: Path):
    for directory, children, files in os.walk(root):
        children[:] = [child for child in children if child not in IGNORED_DIRECTORIES]
        for name in files:
            if name.endswith((".html", ".ejs")):
                yield Path(directory) / name


def read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


@dataclass
class Module:
    path: Path
    root: Node
    source: bytes

    #: nome local -> (especificador, nome importado: nome, "default" ou "*")
    imports: dict[str, tuple[str, str]] = field(default_factory=dict)

    #: nome exportado -> nome local
    exports: dict[str, str] = field(default_factory=dict)

    #: `export * from "x"`
    star_exports: list[str] = field(default_factory=list)

    #: `export { a as b } from "x"`: nome exportado -> (especificador, nome)
    reexports: dict[str, tuple[str, str]] = field(default_factory=dict)

    #: declarações de nível de arquivo: nome -> valor (nó)
    declarations: dict[str, Node] = field(default_factory=dict)

    #: especificadores de todo import, require e import()
    specifiers: list[str] = field(default_factory=list)


class Repository:
    """Os módulos de um sistema e como um import chega a um arquivo."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.modules: dict[Path, Module] = {}
        self.packages: dict[str, Path] = {}
        self._package_dirs: dict[Path, Path] = {}

        for manifest in self._manifests():
            data = read_json(manifest)
            if data and isinstance(data.get("name"), str):
                self.packages.setdefault(data["name"], manifest.parent)

        for path in source_files(self.root):
            module = self._parse(path)
            if module:
                self.modules[path.resolve()] = module

    def _manifests(self):
        for directory, children, files in os.walk(self.root):
            children[:] = [child for child in children if child not in IGNORED_DIRECTORIES]
            if "package.json" in files:
                yield Path(directory) / "package.json"

    def _parse(self, path: Path) -> Module | None:
        try:
            source = path.read_bytes()
            tree = Parser(LANGUAGES[path.suffix]).parse(source)
        except Exception:
            return None

        module = Module(path.resolve(), tree.root_node, source)

        for node in walk(tree.root_node):

            if node.type == "import_statement":
                self._import(node, module)

            elif node.type == "export_statement":
                self._export(node, module)

            elif node.type == "call_expression":
                function = node.child_by_field_name("function")
                arguments = arguments_of(node)
                if function is not None and arguments and text(function, source) in ("require", "import"):
                    value = string_of(arguments[0], source)
                    if value:
                        module.specifiers.append(value)

            elif node.type == "variable_declarator" and self._top_level(node):
                name = node.child_by_field_name("name")
                value = node.child_by_field_name("value")
                if name is not None and value is not None:
                    if name.type == "identifier":
                        module.declarations[text(name, source)] = unwrap(value)
                    self._require(name, unwrap(value), module)

            elif node.type in ("function_declaration", "class_declaration", "enum_declaration") and self._top_level(node):
                name = node.child_by_field_name("name")
                if name is not None:
                    module.declarations[text(name, source)] = node

        return module

    @staticmethod
    def _top_level(node: Node) -> bool:
        """Declaração fora de qualquer função: o que o módulo inteiro enxerga."""
        parent = node.parent
        while parent is not None:
            if is_function(parent) or parent.type == "class_body":
                return False
            parent = parent.parent
        return True

    def _require(self, name: Node, value: Node, module: Module) -> None:
        """`const x = require("m")` e `const { a } = require("m")`."""
        if value.type != "call_expression":
            return
        function = value.child_by_field_name("function")
        arguments = arguments_of(value)
        if function is None or text(function, module.source) != "require" or not arguments:
            return
        specifier = string_of(arguments[0], module.source)
        if not specifier:
            return
        if name.type == "identifier":
            module.imports[text(name, module.source)] = (specifier, "*")
        elif name.type == "object_pattern":
            for child in name.named_children:
                if child.type == "shorthand_property_identifier_pattern":
                    local = text(child, module.source)
                    module.imports[local] = (specifier, local)

    def _import(self, node: Node, module: Module) -> None:
        source = module.source
        specifier_node = node.child_by_field_name("source")
        if specifier_node is None:
            return
        specifier = string_of(specifier_node, source)
        if not specifier:
            return
        module.specifiers.append(specifier)
        for clause in node.named_children:
            if clause.type != "import_clause":
                continue
            for child in clause.named_children:
                if child.type == "identifier":
                    module.imports[text(child, source)] = (specifier, "default")
                elif child.type == "namespace_import":
                    for inner in child.named_children:
                        if inner.type == "identifier":
                            module.imports[text(inner, source)] = (specifier, "*")
                elif child.type == "named_imports":
                    for item in child.named_children:
                        if item.type != "import_specifier":
                            continue
                        name = item.child_by_field_name("name")
                        alias = item.child_by_field_name("alias")
                        if name is not None:
                            module.imports[text(alias or name, source)] = (specifier, text(name, source))

    def _export(self, node: Node, module: Module) -> None:
        source = module.source
        specifier_node = node.child_by_field_name("source")
        specifier = string_of(specifier_node, source) if specifier_node is not None else None
        if specifier:
            module.specifiers.append(specifier)

        declaration = node.child_by_field_name("declaration")
        value = node.child_by_field_name("value")

        if declaration is not None:
            if declaration.type in ("lexical_declaration", "variable_declaration"):
                for declarator in declaration.named_children:
                    if declarator.type != "variable_declarator":
                        continue
                    name = declarator.child_by_field_name("name")
                    if name is None:
                        continue
                    if name.type == "identifier":
                        module.exports[text(name, source)] = text(name, source)
                    elif name.type == "object_pattern":
                        # export const { bootstrap, mount, unmount } = lifecycles
                        for child in name.named_children:
                            if child.type == "shorthand_property_identifier_pattern":
                                module.exports[text(child, source)] = text(child, source)
                            elif child.type == "pair_pattern":
                                key = child.child_by_field_name("key")
                                if key is not None:
                                    module.exports[text(key, source)] = text(key, source)
            else:
                name = declaration.child_by_field_name("name")
                if name is not None:
                    module.exports[text(name, source)] = text(name, source)
            return

        if value is not None:
            value = unwrap(value)
            if value.type == "identifier":
                module.exports["default"] = text(value, source)
            else:
                module.declarations["default"] = value
                module.exports["default"] = "default"
            return

        if specifier and any(child.type == "*" for child in node.children) and not any(
            child.type in ("export_clause", "namespace_export") for child in node.named_children
        ):
            module.star_exports.append(specifier)
            return

        for clause in node.named_children:
            if clause.type != "export_clause":
                continue
            for item in clause.named_children:
                if item.type != "export_specifier":
                    continue
                name = item.child_by_field_name("name")
                alias = item.child_by_field_name("alias")
                if name is None:
                    continue
                exported = text(alias or name, source)
                if specifier:
                    module.reexports[exported] = (specifier, text(name, source))
                else:
                    module.exports[exported] = text(name, source)

    # -- resolução ------------------------------------------------------

    def resolve(self, specifier: str, importer: Path) -> Path | None:
        """O arquivo do repositório que o especificador importa, ou `None`."""

        if specifier.startswith("."):
            return self._file(importer.parent / specifier)

        for name in sorted(self.packages, key=len, reverse=True):
            if specifier == name:
                return self._entry(self.packages[name])
            if specifier.startswith(name + "/"):
                return self._file(self.packages[name] / specifier[len(name) + 1:])

        return None

    def _file(self, base: Path) -> Path | None:
        candidates = [base] + [Path(f"{base}{ext}") for ext in EXTENSIONS] + [base / f"index{ext}" for ext in EXTENSIONS]
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in self.modules:
                return resolved
        return None

    def _entry(self, directory: Path) -> Path | None:
        data = read_json(directory / "package.json") or {}
        for key in ("source", "module", "main", "types", "typings"):
            value = data.get(key)
            if isinstance(value, str):
                value = re.sub(r"\.d\.ts$", "", value)
                value = re.sub(r"\.(js|mjs|cjs|ts|tsx|jsx)$", "", value)
                found = self._file(directory / value)
                if found:
                    return found
                # `dist/index.js` não existe no fonte: tenta o mesmo nome em src/
                found = self._file(directory / "src" / Path(value).name)
                if found:
                    return found
        for fallback in ("src/index", "lib/index", "index"):
            found = self._file(directory / fallback)
            if found:
                return found
        return None

    def package_dir(self, path: Path) -> Path:
        """O diretório do `package.json` mais próximo, sem sair do sistema."""
        directory = path.parent if path.is_file() else path
        directory = directory.resolve()
        if directory in self._package_dirs:
            return self._package_dirs[directory]
        current = directory
        found = self.root
        while True:
            if (current / "package.json").is_file():
                found = current
                break
            if current == self.root or current.parent == current:
                break
            current = current.parent
        self._package_dirs[directory] = found
        return found

    def imported_files(self, module: Module) -> list[Path]:
        found = []
        for specifier in module.specifiers:
            target = self.resolve(specifier, module.path)
            if target:
                found.append(target)
        return found

    # -- símbolos ---------------------------------------------------------

    def origin(self, module: Module, name: str, depth: int = 0) -> tuple[Module, str] | tuple[str, str] | None:
        """
        Onde o nome é declarado: (módulo, nome local) no repositório, ou
        (especificador, nome importado) quando vem de uma biblioteca.
        """

        if depth > 8:
            return None

        if name in module.imports:
            specifier, imported = module.imports[name]
            target = self.resolve(specifier, module.path)
            if target is None:
                return specifier, imported
            if imported == "*":
                return self.modules[target], "*"
            return self.exported(self.modules[target], imported, depth + 1)

        if name in module.declarations:
            return module, name

        return None

    def exported(self, module: Module, name: str, depth: int = 0):
        if depth > 8:
            return None
        if name in module.exports:
            local = module.exports[name]
            return self.origin(module, local, depth + 1) or (module, local)
        if name in module.reexports:
            specifier, imported = module.reexports[name]
            target = self.resolve(specifier, module.path)
            if target is None:
                return specifier, imported
            return self.exported(self.modules[target], imported, depth + 1)
        for specifier in module.star_exports:
            target = self.resolve(specifier, module.path)
            if target is not None:
                found = self.exported(self.modules[target], name, depth + 1)
                if found:
                    return found
        return None

    def relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)


# ----------------------------------------------------------------------
# Valores: canal, chave de storage
# ----------------------------------------------------------------------


class Values:
    """Resolve o texto de um canal ou de uma chave, seguindo constantes."""

    def __init__(self, repository: Repository):
        self.repository = repository

    def of(self, node: Node | None, module: Module, depth: int = 0) -> str | None:
        if node is None or depth > 6:
            return None
        node = unwrap(node)
        source = module.source

        literal = string_of(node, source)
        if literal is not None:
            return literal

        if node.type == "template_string":
            parts, known = [], False
            for child in node.named_children:
                if child.type in ("string_fragment", "escape_sequence"):
                    parts.append(text(child, source))
                    known = True
                elif child.type == "template_substitution":
                    inner = next((item for item in child.named_children), None)
                    value = self.of(inner, module, depth + 1)
                    parts.append(value if value is not None else PARAM)
                    known = known or value is not None
            return "".join(parts) if known else None

        if node.type == "binary_expression" and text(node.child_by_field_name("operator"), source) == "+":
            left = self.of(node.child_by_field_name("left"), module, depth + 1)
            right = self.of(node.child_by_field_name("right"), module, depth + 1)
            if left is None and right is None:
                return None
            return (left if left is not None else PARAM) + (right if right is not None else PARAM)

        if node.type == "identifier":
            declared = self._declared(module, text(node, source), depth)
            if declared is not None:
                owner, value = declared
                if value.type not in ("object", "enum_declaration"):
                    return self.of(value, owner, depth + 1)
            return None

        if node.type == "member_expression":
            target = node.child_by_field_name("object")
            prop = node.child_by_field_name("property")
            if target is None or prop is None:
                return None
            container = self._container(target, module, depth)
            if container is None:
                return None
            owner, value = container
            return self._member(value, text(prop, source), owner, depth)

        return None

    def _declared(self, module: Module, name: str, depth: int):
        found = self.repository.origin(module, name)
        if not found or not isinstance(found[0], Module):
            return None
        owner, local = found
        value = owner.declarations.get(local)
        return (owner, value) if value is not None else None

    def _container(self, node: Node, module: Module, depth: int):
        node = unwrap(node)
        if node.type == "identifier":
            return self._declared(module, text(node, module.source), depth)
        if node.type == "member_expression":
            outer = self._container(node.child_by_field_name("object"), module, depth + 1)
            prop = node.child_by_field_name("property")
            if outer is None or prop is None:
                return None
            owner, value = outer
            if value.type == "object":
                inner = object_property(value, text(prop, owner.source), owner.source)
                return (owner, inner) if inner is not None else None
        return None

    def _member(self, container: Node, name: str, owner: Module, depth: int) -> str | None:
        if container.type == "object":
            value = object_property(container, name, owner.source)
            return self.of(value, owner, depth + 1) if value is not None else None
        if container.type == "enum_declaration":
            body = container.child_by_field_name("body")
            for child in (body.named_children if body is not None else []):
                if child.type == "enum_assignment":
                    key = child.child_by_field_name("name")
                    value = child.child_by_field_name("value")
                    if key is not None and text(key, owner.source) == name:
                        return self.of(value, owner, depth + 1)
        return None


# ----------------------------------------------------------------------
# Papéis: o que um identificador é (seletor, barramento, embrulho de storage…)
# ----------------------------------------------------------------------


class Roles:
    """
    O papel de um nome: vem de uma biblioteca do catálogo, ou de uma
    declaração do repositório construída a partir de uma.
    """

    def __init__(self, repository: Repository, values: Values):
        self.repository = repository
        self.values = values
        self._cache: dict[tuple[Path, str], tuple | None] = {}
        self._busy: set[tuple[Path, str]] = set()

    def of_name(self, module: Module, name: str) -> tuple | None:
        found = self.repository.origin(module, name)
        if found is None:
            return None
        owner, local = found
        if not isinstance(owner, Module):
            return LIBRARY_ROLES.get((owner, local))
        if local == "*":
            return None
        return self._declared(owner, local)

    def of_node(self, node: Node | None, module: Module) -> tuple | None:
        if node is None:
            return None
        node = unwrap(node)
        source = module.source
        if node.type == "identifier":
            return self.of_name(module, text(node, source))
        if node.type == "member_expression":
            target = unwrap(node.child_by_field_name("object"))
            prop = node.child_by_field_name("property")
            if target is None or prop is None:
                return None
            # namespace: `import * as bus from "./bus"; bus.emitter`
            if target.type == "identifier":
                found = self.repository.origin(module, text(target, source))
                if found and isinstance(found[0], Module) and found[1] == "*":
                    exported = self.repository.exported(found[0], text(prop, source))
                    if exported and isinstance(exported[0], Module):
                        return self._declared(*exported)
                    if exported:
                        return LIBRARY_ROLES.get(exported)
                if found and isinstance(found[0], str) and found[1] == "*":
                    return LIBRARY_ROLES.get((found[0], text(prop, source)))
                # objeto do módulo com métodos: `storage.get(key)`
                if found and isinstance(found[0], Module):
                    return self._declared(found[0], f"{found[1]}.{text(prop, source)}")
        return None

    def _declared(self, module: Module, name: str) -> tuple | None:
        key = (module.path, name)
        if key in self._cache:
            return self._cache[key]
        if key in self._busy:
            return None
        self._busy.add(key)
        try:
            role = self._compute(module, name)
        finally:
            self._busy.discard(key)
        self._cache[key] = role
        return role

    def _compute(self, module: Module, name: str) -> tuple | None:
        source = module.source

        if "." in name:
            base, _, method = name.partition(".")
            container = module.declarations.get(base)
            if container is None or container.type != "object":
                return None
            for child in container.named_children:
                if child.type == "pair" and property_key(child, source) == method:
                    return self._function_role(unwrap(child.child_by_field_name("value")), module)
                if child.type == "method_definition":
                    method_name = child.child_by_field_name("name")
                    if method_name is not None and text(method_name, source) == method:
                        return self._function_role(child, module)
            return None

        value = module.declarations.get(name)
        if value is None:
            return None

        if is_function(value):
            return self._function_role(value, module)

        if value.type == "identifier":
            role = self.of_name(module, text(value, source))
            # `export const useAppSelector: TypedUseSelectorHook<S> = useSelector`
            return role if role and role[0] in ("selector", "bus", "zustand-hook", "pinia") else None

        if value.type == "new_expression":
            role = self.of_node(callee(value), module)
            if role and role[0] == "bus-class":
                return ("bus", role[1])
            return None

        if value.type == "call_expression":
            function = unwrap(callee(value))
            # `create<T>()(...)`: a chamada de dentro é a do zustand
            inner = function
            while inner is not None and inner.type == "call_expression":
                inner = unwrap(callee(inner))
            role = self.of_node(inner, module)
            # `useSelector.withTypes<RootState>()`
            if role is None and function is not None and function.type == "member_expression":
                prop = function.child_by_field_name("property")
                if prop is not None and text(prop, source) == "withTypes":
                    role = self.of_node(function.child_by_field_name("object"), module)
                    return role if role and role[0] == "selector" else None
            if role is None:
                return None
            if role[0] == "bus-factory":
                return ("bus", role[1])
            if role[0] == "zustand-create":
                return ("zustand-hook", f"{self.repository.relative(module.path)}#{name}")
            if role[0] == "pinia-define":
                arguments = arguments_of(value)
                store = None
                if arguments:
                    store = self.values.of(arguments[0], module)
                    if store is None and unwrap(arguments[0]).type == "object":
                        store = self.values.of(object_property(unwrap(arguments[0]), "id", source), module)
                return ("pinia", store or f"{self.repository.relative(module.path)}#{name}")
        return None

    def _function_role(self, function: Node | None, module: Module) -> tuple | None:
        """Função que repassa um parâmetro seu como chave do storage."""

        if not is_function(function):
            return None
        source = module.source
        parameters = parameters_of(function, source)
        if not any(parameters):
            return None
        body = function.child_by_field_name("body")
        if body is None:
            return None
        forwards = []
        for node in walk(body):
            if node.type != "call_expression":
                continue
            access = storage_call(node, source)
            if access is None:
                continue
            kind, verb, arguments = access
            if verb == "clear" or not arguments:
                continue
            key = unwrap(arguments[0])
            if key.type == "identifier" and text(key, source) in parameters:
                forwards.append((kind, parameters.index(text(key, source)), STORAGE_ACCESS[verb]))
        return ("storage-wrapper", tuple(sorted(set(forwards)))) if forwards else None


def storage_call(call: Node, source: bytes):
    """`localStorage.getItem(...)`, `window.sessionStorage.setItem(...)`: (tipo, verbo, argumentos)."""
    function = callee(call)
    if function is None or function.type != "member_expression":
        return None
    prop = function.child_by_field_name("property")
    target = function.child_by_field_name("object")
    if prop is None or target is None:
        return None
    verb = text(prop, source)
    if verb not in STORAGE_ACCESS:
        return None
    kind = text(target, source).replace("?", "").rpartition(".")[2]
    if kind not in STORAGES:
        return None
    return kind, verb, arguments_of(call)


# ----------------------------------------------------------------------
# Micro frontends
# ----------------------------------------------------------------------


@dataclass
class Unit:
    name: str
    directory: Path | None
    found_by: set[str] = field(default_factory=set)
    role: str = "micro frontend"

    #: chaves de customProps recebidas, do registerApplication
    custom_props: set[str] = field(default_factory=set)

    #: diretório de quem a registrou
    registered_by: Path | None = None


def unscoped(name: str) -> str:
    return name.rpartition("/")[2]


class Discovery:

    def __init__(self, repository: Repository, values: Values):
        self.repository = repository
        self.values = values

    def units(self) -> list[Unit]:
        by_directory: dict[Path, Unit] = {}
        without_directory: dict[str, Unit] = {}

        def add(name: str, directory: Path | None, how: str) -> Unit:
            if directory is not None and directory in by_directory:
                unit = by_directory[directory]
            elif directory is None and name in without_directory:
                unit = without_directory[name]
            else:
                unit = Unit(name, directory)
                if directory is not None:
                    by_directory[directory] = unit
                else:
                    without_directory[name] = unit
            unit.found_by.add(how)
            return unit

        # Ciclos de vida do single-spa e federação: a unidade se declara.
        for module in self.repository.modules.values():
            if LIFECYCLES.issubset(module.exports):
                directory = self.repository.package_dir(module.path)
                if self._installable(directory):
                    add(self._package_name(directory), directory, "ciclos de vida single-spa")
            if module.path.name.startswith(FEDERATION_CONFIGS):
                for name in self._federations(module):
                    add(name, self.repository.package_dir(module.path), "Module Federation")

        # Registro no orquestrador e layout.
        registered: list[tuple[str, Path, set[str], str]] = []
        for module in self.repository.modules.values():
            for name, props in self._registrations(module):
                registered.append((name, module.path, props, "registerApplication"))
        for path in layout_files(self.repository.root):
            for name in self._layout(path):
                registered.append((name, path, set(), "layout"))

        for name, declared_in, props, how in registered:
            orchestrator_dir = self.repository.package_dir(declared_in)
            orchestrator = add(self._package_name(orchestrator_dir), orchestrator_dir, "orquestrador")
            orchestrator.role = "orquestrador"
            directory = self._directory_of(name, by_directory)
            if directory == orchestrator_dir:
                directory = None
            unit = add(name, directory, how)
            unit.custom_props |= props
            unit.registered_by = orchestrator_dir

        units = list(by_directory.values()) + [
            unit for name, unit in without_directory.items()
            if not any(self._same(name, other.name) for other in by_directory.values())
        ]

        # Nomes repetidos (dois `@org/root-config`) ficam com o do diretório.
        counts = defaultdict(int)
        for unit in units:
            counts[unit.name] += 1
        for unit in units:
            if counts[unit.name] > 1 and unit.directory is not None:
                unit.name = unit.directory.name

        return sorted(units, key=lambda unit: unit.name)

    @staticmethod
    def _same(a: str, b: str) -> bool:
        return a == b or unscoped(a) == unscoped(b)

    def _directory_of(self, name: str, by_directory: dict[Path, Unit]) -> Path | None:
        for directory, unit in by_directory.items():
            if self._same(name, unit.name):
                return directory
        if name in self.repository.packages:
            return self.repository.packages[name].resolve()
        for package, directory in self.repository.packages.items():
            if self._same(name, package):
                return directory.resolve()
        for directory in by_directory:
            if directory.name == unscoped(name):
                return directory
        return None

    def _package_name(self, directory: Path) -> str:
        data = read_json(directory / "package.json") or {}
        name = data.get("name")
        return name if isinstance(name, str) and name else directory.name

    @staticmethod
    def _installable(directory: Path) -> bool:
        """Um `package.json` que não é JSON é molde de gerador, não MFE."""
        manifest = directory / "package.json"
        return not manifest.is_file() or read_json(manifest) is not None

    def _registrations(self, module: Module):
        source = module.source
        for node in walk(module.root):
            if node.type != "call_expression":
                continue
            function = callee(node)
            if function is None or last_name(function, source) != "registerApplication":
                continue
            arguments = arguments_of(node)
            if not arguments:
                continue
            first = unwrap(arguments[0])
            props: set[str] = set()
            if first.type == "object":
                name = self.values.of(object_property(first, "name", source), module)
                custom = object_property(first, "customProps", source)
            else:
                name = self.values.of(first, module)
                custom = unwrap(arguments[3]) if len(arguments) > 3 else None
            if custom is not None and custom.type == "object":
                props = set(object_keys(custom, source))
            if name:
                yield name, props

    @staticmethod
    def _layout(path: Path) -> list[str]:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []
        if "single-spa-router" not in content and "single-spa-layout" not in content:
            return []
        # O gerador deixa exemplos comentados (`@org/navbar`): não são unidades.
        content = re.sub(r"<!--.*?-->", "", content, flags=re.S)
        return re.findall(r"<application\b[^>]*\bname=[\"']([^\"']+)[\"']", content)

    def _federations(self, module: Module) -> list[str]:
        source = module.source
        names = []
        candidates = []
        for node in walk(module.root):
            if node.type in ("call_expression", "new_expression"):
                function = callee(node)
                if function is not None and last_name(function, source) in FEDERATION_CALLS:
                    for argument in arguments_of(node):
                        argument = unwrap(argument)
                        if argument.type == "identifier":
                            argument = module.declarations.get(text(argument, source))
                        if argument is not None and argument.type == "object":
                            candidates.append(argument)
        if module.path.name.startswith(("module-federation.config", "federation.config")):
            default = module.declarations.get(module.exports.get("default", ""))
            if default is not None and default.type == "object":
                candidates.append(default)
            for node in walk(module.root):
                # module.exports = { name, exposes }
                if node.type == "assignment_expression" and text(node.child_by_field_name("left"), source) == "module.exports":
                    right = unwrap(node.child_by_field_name("right"))
                    if right is not None and right.type == "object":
                        candidates.append(right)
        for candidate in candidates:
            name = self._federation_name(candidate, module)
            if name:
                names.append(name)
        return names

    def _federation_name(self, candidate: Node, module: Module, depth: int = 0) -> str | None:
        """O `name` do objeto, também quando vem espalhado: `federation({ ...config })`."""
        source = module.source
        name = self.values.of(object_property(candidate, "name", source), module)
        if name or depth > 3:
            return name
        for child in candidate.named_children:
            if child.type == "spread_element":
                inner = next(iter(child.named_children), None)
                if inner is not None and inner.type == "identifier":
                    declared = module.declarations.get(text(inner, source))
                    if declared is not None and declared.type == "object":
                        name = self._federation_name(declared, module, depth + 1)
                        if name:
                            return name
        return None


class Ownership:
    """De que MFE é cada arquivo; código de pacote comum é de quem o importa."""

    def __init__(self, repository: Repository, units: list[Unit]):
        self.repository = repository
        self.directories = sorted(
            ((unit.directory, unit.name) for unit in units if unit.directory is not None),
            key=lambda item: len(item[0].parts),
            reverse=True,
        )
        self.owner: dict[Path, str | None] = {path: self._of(path) for path in repository.modules}
        self.shared: dict[Path, set[str]] = defaultdict(set)
        self._spread()

    def _of(self, path: Path) -> str | None:
        for directory, name in self.directories:
            if path == directory or directory in path.parents:
                return name
        return None

    def _spread(self) -> None:
        for path, owner in self.owner.items():
            if owner is None:
                continue
            stack = [
                target for target in self.repository.imported_files(self.repository.modules[path])
                if self.owner.get(target) is None
            ]
            seen = set()
            while stack:
                current = stack.pop()
                if current in seen:
                    continue
                seen.add(current)
                self.shared[current].add(owner)
                stack.extend(
                    target for target in self.repository.imported_files(self.repository.modules[current])
                    if self.owner.get(target) is None
                )

    def of(self, path: Path) -> list[str]:
        owner = self.owner.get(path)
        if owner:
            return [owner]
        return sorted(self.shared.get(path, ()))


# ----------------------------------------------------------------------
# Comunicação
# ----------------------------------------------------------------------


@dataclass
class Occurrence:
    mechanism: str
    channel: str
    side: str
    file: Path
    line: int
    code: str
    microfrontend: str = ""
    private: bool = False


class Extractor:

    def __init__(self, repository: Repository, values: Values, roles: Roles):
        self.repository = repository
        self.values = values
        self.roles = roles

    def occurrences(self, module: Module) -> list[Occurrence]:
        source = module.source
        found: list[Occurrence] = []
        channels = self._broadcast_channels(module)
        events = self._event_variables(module)

        def add(mechanism, channel, side, node):
            if channel is None or channel == "":
                return
            code = " ".join(text(node, source).split())[:160]
            found.append(Occurrence(mechanism, channel, side, module.path, node.start_point[0] + 1, code))

        for node in walk(module.root):

            if node.type == "assignment_expression":
                left = node.child_by_field_name("left")
                if left is not None and left.type == "member_expression":
                    prop = left.child_by_field_name("property")
                    target = text(left.child_by_field_name("object"), source)
                    if prop is not None and text(prop, source) == "onmessage" and target in channels:
                        add("BroadcastChannel", channels[target], "consome", node)
                continue

            if node.type != "call_expression":
                continue

            function = unwrap(callee(node))
            if function is None:
                continue
            name = last_name(function, source)
            arguments = arguments_of(node)
            receiver = function.child_by_field_name("object") if function.type == "member_expression" else None
            receiver_text = text(receiver, source) if receiver is not None else ""

            # Storage do navegador
            access = storage_call(node, source)
            if access is not None:
                kind, verb, args = access
                key = ALL_KEYS if verb == "clear" else (self.values.of(args[0], module) if args else None)
                add(kind, key, STORAGE_ACCESS[verb], node)
                continue

            # CustomEvent
            # Evento atravessa MFEs só pelos alvos globais; num elemento é da página.
            global_target = receiver is None or receiver_text.replace("?", "") in GLOBAL_TARGETS

            if name == "dispatchEvent" and arguments and global_target:
                event = unwrap(arguments[0])
                if event.type == "identifier":
                    event = events.get(text(event, source), event)
                if event.type == "new_expression":
                    constructor = event.child_by_field_name("constructor")
                    inner = arguments_of(event)
                    if constructor is not None and text(constructor, source) in ("CustomEvent", "Event") and inner:
                        channel = self.values.of(inner[0], module) or text(inner[0], source)
                        if channel not in NATIVE_EVENTS:
                            add("CustomEvent", channel, "produz", node)
                continue

            if name == "addEventListener" and arguments:
                channel = self.values.of(arguments[0], module)
                if channel == "message":
                    if receiver_text in channels:
                        add("BroadcastChannel", channels[receiver_text], "consome", node)
                    elif len(arguments) > 1:
                        for literal in self._compared_literals(arguments[1], module):
                            add("postMessage", literal, "consome", node)
                elif not global_target:
                    pass
                elif channel is None and unwrap(arguments[0]).type in ("identifier", "member_expression"):
                    add("CustomEvent", text(arguments[0], source), "consome", node)
                elif channel and channel not in NATIVE_EVENTS:
                    add("CustomEvent", channel, "consome", node)
                continue

            if name == "fromEvent" and len(arguments) >= 2:
                if text(arguments[0], source) in GLOBAL_TARGETS:
                    channel = self.values.of(arguments[1], module) or text(arguments[1], source)
                    if channel not in NATIVE_EVENTS:
                        add("CustomEvent", channel, "consome", node)
                continue

            if name == "postMessage":
                if receiver_text in channels:
                    add("BroadcastChannel", channels[receiver_text], "produz", node)
                elif len(arguments) >= 2:
                    add("postMessage", self._message_type(arguments[0], module), "produz", node)
                continue

            # Biblioteca de estado, barramento, embrulho de storage
            role = self.roles.of_node(function, module)
            if role is None and receiver is not None:
                receiver_role = self.roles.of_node(receiver, module)
                if receiver_role and receiver_role[0] == "bus":
                    produce, consume = BUSES[receiver_role[1]]
                    channel = self.values.of(arguments[0], module) if arguments else None
                    if name in produce:
                        add(receiver_role[1], channel, "produz", node)
                    elif name in consume:
                        add(receiver_role[1], channel, "consome", node)
                    continue

            if role is not None:
                kind = role[0]
                if kind == "selector":
                    for path in self._selected(arguments[0] if arguments else None, module):
                        add("redux", path, "lê", node)
                elif kind == "store-factory":
                    found.append(Occurrence("redux-store", "", "cria", module.path, node.start_point[0] + 1, ""))
                elif kind == "zustand-hook":
                    paths = self._selected(arguments[0], module) if arguments else []
                    for path in paths or [""]:
                        add("zustand", role[1] + (f".{path}" if path else ""), "lê", node)
                elif kind == "pinia":
                    add("pinia", role[1], "lê", node)
                elif kind == "atom-hook" and arguments:
                    add(role[1], self._identity(arguments[0], module), role[2], node)
                elif kind == "storage-wrapper":
                    for storage, index, side in role[1]:
                        if index < len(arguments):
                            add(storage, self.values.of(arguments[index], module), side, node)
                continue

            # Subject do rxjs importado de outro módulo
            if name in ("next", "subscribe") and receiver is not None and receiver.type in ("identifier", "member_expression"):
                root_name = receiver_text.split(".")[0].split("?")[0]
                if root_name in module.imports:
                    specifier, _ = module.imports[root_name]
                    if specifier not in RX_INTERNAL:
                        identity = self._identity_text(module, root_name, receiver_text)
                        add("rxjs-subject", identity, "produz" if name == "next" else "consome", node)

        return found

    def _identity(self, node: Node, module: Module) -> str:
        node = unwrap(node)
        source_text = text(node, module.source)
        root_name = source_text.split(".")[0]
        return self._identity_text(module, root_name, source_text)

    def _identity_text(self, module: Module, root_name: str, full: str) -> str:
        """`módulo#caminho`: o mesmo símbolo importado por dois MFEs é o mesmo canal."""
        found = self.repository.origin(module, root_name)
        rest = full[len(root_name):]
        if found is None:
            return f"{self.repository.relative(module.path)}#{full}"
        owner, local = found
        where = self.repository.relative(owner.path) if isinstance(owner, Module) else owner
        return f"{where}#{local}{rest}" if local != "*" else f"{where}#{rest.lstrip('.')}"

    def _broadcast_channels(self, module: Module) -> dict[str, str]:
        """Variáveis e campos que guardam um `new BroadcastChannel(canal)`."""
        source = module.source
        found = {}
        for node in walk(module.root):
            if node.type != "new_expression":
                continue
            constructor = node.child_by_field_name("constructor")
            arguments = arguments_of(node)
            if constructor is None or text(constructor, source) != "BroadcastChannel" or not arguments:
                continue
            channel = self.values.of(arguments[0], module) or text(arguments[0], source)
            parent = node.parent
            while parent is not None and parent.type in ("parenthesized_expression", "as_expression"):
                parent = parent.parent
            if parent is None:
                continue
            if parent.type == "variable_declarator":
                found[text(parent.child_by_field_name("name"), source)] = channel
            elif parent.type == "assignment_expression":
                found[text(parent.child_by_field_name("left"), source)] = channel
            elif parent.type in ("public_field_definition", "field_definition"):
                name = parent.child_by_field_name("name") or parent.child_by_field_name("property")
                if name is not None:
                    found[f"this.{text(name, source)}"] = channel
        return found

    def _event_variables(self, module: Module) -> dict[str, Node]:
        """`const e = new CustomEvent(...)`, para o `dispatchEvent(e)`."""
        found = {}
        for node in walk(module.root):
            if node.type == "variable_declarator":
                value = node.child_by_field_name("value")
                name = node.child_by_field_name("name")
                if value is not None and name is not None and unwrap(value).type == "new_expression":
                    found[text(name, module.source)] = unwrap(value)
        return found

    def _message_type(self, payload: Node, module: Module) -> str | None:
        payload = unwrap(payload)
        if payload.type != "object":
            return None
        for name in MESSAGE_TYPE_FIELDS:
            value = object_property(payload, name, module.source)
            if value is not None:
                resolved = self.values.of(value, module)
                if resolved:
                    return resolved
        return None

    def _compared_literals(self, handler: Node, module: Module) -> list[str]:
        """Os tipos que o listener de "message" trata: `data.type === "x"` e `case "x":`."""
        source = module.source
        handler = unwrap(handler)
        if handler.type == "identifier":
            handler = module.declarations.get(text(handler, source), handler)
        found = []

        def is_type_field(node: Node | None) -> bool:
            if node is None:
                return False
            node = unwrap(node)
            if node.type != "member_expression":
                return False
            prop = node.child_by_field_name("property")
            return prop is not None and text(prop, source) in MESSAGE_TYPE_FIELDS

        for node in walk(handler):
            if node.type == "binary_expression":
                operator = node.child_by_field_name("operator")
                if operator is None or text(operator, source) not in ("===", "=="):
                    continue
                left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
                for field_side, literal_side in ((left, right), (right, left)):
                    if is_type_field(field_side):
                        value = self.values.of(literal_side, module)
                        if value:
                            found.append(value)
            elif node.type == "switch_statement" and is_type_field(node.child_by_field_name("value")):
                for case in walk(node.child_by_field_name("body")):
                    if case.type == "switch_case":
                        value = self.values.of(case.child_by_field_name("value"), module)
                        if value:
                            found.append(value)
        return sorted(set(found))

    def _selected(self, selector: Node | None, module: Module) -> list[str]:
        """`(state) => state.cart.items` → `cart.items`; `({ a: s.a, b: s.b })` → `a`, `b`."""
        if selector is None:
            return []
        source = module.source
        selector = unwrap(selector)
        if not is_function(selector):
            return [text(selector, source)]
        parameters = parameters_of(selector, source)
        if not parameters or not parameters[0]:
            return []
        state = parameters[0]
        body = selector.child_by_field_name("body")
        paths = set()
        for node in walk(body):
            if node.type != "member_expression":
                continue
            parent = node.parent
            if parent is not None and parent.type == "member_expression" and parent.child_by_field_name("object") == node:
                continue
            chain = text(node, source).replace("?.", ".").split(".")
            if chain[0] == state and len(chain) > 1:
                paths.add(".".join(chain[1:]))
        return sorted(paths)


# ----------------------------------------------------------------------
# Sistema
# ----------------------------------------------------------------------


def analyze(root: Path) -> dict:
    repository = Repository(root)
    values = Values(repository)
    roles = Roles(repository, values)
    units = Discovery(repository, values).units()
    ownership = Ownership(repository, units)
    extractor = Extractor(repository, values, roles)

    occurrences: list[Occurrence] = []
    private_stores: set[str] = set()

    for path, module in repository.modules.items():
        owners = ownership.of(path)
        if not owners:
            continue
        for occurrence in extractor.occurrences(module):
            for owner in owners:
                if occurrence.mechanism == "redux-store":
                    # store criado dentro do MFE é dele; em pacote comum, não
                    if ownership.owner.get(path) == owner:
                        private_stores.add(owner)
                    continue
                occurrences.append(Occurrence(**{**occurrence.__dict__, "microfrontend": owner}))

    for occurrence in occurrences:
        if occurrence.mechanism == "redux" and occurrence.microfrontend in private_stores:
            occurrence.private = True

    # customProps: do orquestrador que registra para o MFE registrado
    names_by_dir = {unit.directory: unit.name for unit in units if unit.directory is not None}
    links: list[dict] = []
    for unit in units:
        source_name = names_by_dir.get(unit.registered_by)
        for key in sorted(unit.custom_props):
            occurrences.append(Occurrence("customProps", key, "produz", unit.registered_by or repository.root, 0, "customProps", source_name or "?"))
            if source_name and source_name != unit.name:
                links.append({"mecanismo": "customProps", "tipo": MESSAGE, "canal": key, "de": source_name, "para": unit.name})

    links += pair(occurrences)

    by_mechanism: dict[str, dict] = {}
    for occurrence in occurrences:
        entry = by_mechanism.setdefault(occurrence.mechanism, {
            "tipo": MECHANISMS[occurrence.mechanism], "ocorrencias": 0, "canais": set(),
            "mfes": set(), "canais_entre_mfes": set(), "ligacoes": 0,
        })
        entry["ocorrencias"] += 1
        entry["canais"].add(occurrence.channel)
        entry["mfes"].add(occurrence.microfrontend)
    for link in links:
        entry = by_mechanism[link["mecanismo"]]
        entry["canais_entre_mfes"].add(link["canal"])
        entry["ligacoes"] += 1

    summary = {
        mechanism: {
            "tipo": entry["tipo"],
            "ocorrencias": entry["ocorrencias"],
            "canais": len(entry["canais"]),
            "canais_entre_mfes": len(entry["canais_entre_mfes"]),
            "ligacoes": entry["ligacoes"],
            "mfes": sorted(entry["mfes"]),
        }
        for mechanism, entry in sorted(by_mechanism.items())
    }

    return {
        "sistema": root.name,
        "microfrontends": {
            "total": sum(1 for unit in units if counted(unit)),
            # registrados, mas cujo código não está no sistema
            "sem_codigo": sorted(unit.name for unit in units if unit.directory is None),
            "lista": [
                {
                    "nome": unit.name,
                    "diretorio": repository.relative(unit.directory) if unit.directory else None,
                    "papel": unit.role,
                    "encontrado_por": sorted(unit.found_by),
                }
                for unit in units
                if counted(unit)
            ],
        },
        "comunicacao": summary,
        "tipos_entre_mfes": sorted(mechanism for mechanism, entry in summary.items() if entry["ligacoes"]),
        "ligacoes": links,
        "ocorrencias": [
            {
                "microfrontend": item.microfrontend, "mecanismo": item.mechanism, "canal": item.channel,
                "lado": item.side, "arquivo": repository.relative(item.file), "linha": item.line,
                "codigo": item.code, **({"store_proprio": True} if item.private else {}),
            }
            for item in sorted(occurrences, key=lambda item: (item.mechanism, item.channel, item.microfrontend, str(item.file), item.line))
        ],
    }


def counted(unit: Unit) -> bool:
    """
    Unidade com código no sistema, ou registrada por `registerApplication`
    mesmo sem o código (é um nó do sistema, como no DAMFE). Nome que só
    aparece no layout, sem código, fica de fora: costuma ser exemplo do
    gerador ou unidade de outro sistema.
    """
    return unit.directory is not None or "registerApplication" in unit.found_by


def pair(occurrences: list[Occurrence]) -> list[dict]:
    """
    Mensagem: quem produz um canal liga-se a quem o consome, se forem MFEs
    diferentes. Estado: dois MFEs que tocam a mesma chave ou fatia; `clear()`
    toca todas as chaves daquele storage.
    """

    links = []
    messages: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    states: dict[tuple[str, str], set[str]] = defaultdict(set)

    for item in occurrences:
        if item.mechanism == "customProps" or item.private:
            continue
        if MECHANISMS[item.mechanism] == MESSAGE:
            messages[(item.mechanism, item.channel)][item.side].add(item.microfrontend)
        else:
            states[(item.mechanism, item.channel)].add(item.microfrontend)

    for (mechanism, channel), sides in sorted(messages.items()):
        for producer in sorted(sides["produz"]):
            for consumer in sorted(sides["consome"]):
                if producer != consumer:
                    links.append({"mecanismo": mechanism, "tipo": MESSAGE, "canal": channel, "de": producer, "para": consumer})

    clearing = defaultdict(set)
    for (mechanism, channel), mfes in states.items():
        if channel == ALL_KEYS:
            clearing[mechanism] |= mfes

    for (mechanism, channel), mfes in sorted(states.items()):
        if channel == ALL_KEYS:
            continue
        everyone = mfes | clearing.get(mechanism, set())
        if len(everyone) > 1:
            links.append({"mecanismo": mechanism, "tipo": STATE, "canal": channel, "mfes": sorted(everyone)})

    return links


# ----------------------------------------------------------------------
# Saída
# ----------------------------------------------------------------------


def report(result: dict) -> None:
    print(f"\n== {result['sistema']}: {result['microfrontends']['total']} micro frontends")
    if result["microfrontends"]["sem_codigo"]:
        print(f"   registrados sem código no sistema (só os de registerApplication contam): {', '.join(result['microfrontends']['sem_codigo'])}")
    for unit in result["microfrontends"]["lista"]:
        role = " (orquestrador)" if unit["papel"] == "orquestrador" else ""
        print(f"   - {unit['nome']}{role}  [{unit['diretorio'] or 'sem diretório'}]")
    if not result["comunicacao"]:
        print("   nenhuma comunicação encontrada")
        return
    print(f"   {'mecanismo':<17} {'tipo':<14} {'ocorr.':>6} {'canais':>6} {'entre MFEs':>10}")
    for mechanism, entry in result["comunicacao"].items():
        print(f"   {mechanism:<17} {entry['tipo']:<14} {entry['ocorrencias']:>6} {entry['canais']:>6} {entry['canais_entre_mfes']:>10}")
    print(f"   tipos entre MFEs: {', '.join(result['tipos_entre_mfes']) or 'nenhum'}")


def save(results: list[dict], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)

    for result in results:
        (output / f"{result['sistema']}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    with (output / "sistemas.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sistema", "micro_frontends", "orquestradores", "registrados_sem_codigo", "tipos_entre_mfes", "mensagem_entre_mfes", "estado_global_entre_mfes"])
        for result in results:
            types = result["tipos_entre_mfes"]
            writer.writerow([
                result["sistema"],
                result["microfrontends"]["total"],
                sum(1 for unit in result["microfrontends"]["lista"] if unit["papel"] == "orquestrador"),
                len(result["microfrontends"]["sem_codigo"]),
                ";".join(types),
                ";".join(item for item in types if MECHANISMS[item] == MESSAGE),
                ";".join(item for item in types if MECHANISMS[item] == STATE),
            ])

    with (output / "comunicacao.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sistema", "mecanismo", "tipo", "ocorrencias", "canais", "canais_entre_mfes", "ligacoes", "mfes_que_usam"])
        for result in results:
            for mechanism, entry in result["comunicacao"].items():
                writer.writerow([
                    result["sistema"], mechanism, entry["tipo"], entry["ocorrencias"], entry["canais"],
                    entry["canais_entre_mfes"], entry["ligacoes"], len(entry["mfes"]),
                ])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("sistemas", nargs="*", type=Path, help="pasta de um sistema (um ou mais repositórios)")
    parser.add_argument("--pasta", type=Path, help="pasta com um sistema por subpasta")
    parser.add_argument("--saida", type=Path, help="pasta onde gravar sistemas.csv, comunicacao.csv e um JSON por sistema")
    args = parser.parse_args()

    systems = list(args.sistemas)
    if args.pasta:
        systems += sorted(path for path in args.pasta.iterdir() if path.is_dir() and not path.name.startswith("."))
    if not systems:
        parser.error("informe ao menos um sistema ou --pasta")

    results = []
    for system in systems:
        try:
            result = analyze(system)
        except Exception as error:
            print(f"\n== {system.name}: falhou ({error})", file=sys.stderr)
            continue
        report(result)
        results.append(result)

    if args.saida:
        save(results, args.saida)
        print(f"\ngravado em {args.saida}")


if __name__ == "__main__":
    main()
