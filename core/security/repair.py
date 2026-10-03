"""Conservative repair recipe for a standalone Python literal parser.

The structural restriction is intentional: a static eval match alone does not
establish that replacing an expression evaluator preserves an application's API.
"""
import ast
from core.domain.types import PatchEdit


def parser_function(source: str, *, patched: bool = False) -> ast.FunctionDef:
    tree = ast.parse(source)
    body = tree.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.FunctionDef):
        raise ValueError('Repair supports only a standalone one-function literal parser module.')
    function = body[0]
    args = function.args
    if function.decorator_list or function.returns or function.type_params or args.defaults or args.kw_defaults or args.kwonlyargs or args.vararg or args.kwarg or args.posonlyargs or len(args.args) != 1 or args.args[0].annotation:
        raise ValueError('Parser signatures with executable metadata or extra arguments are unsupported.')
    statements = function.body
    if patched:
        if len(statements) != 2 or ast.dump(statements[0], include_attributes=False) != ast.dump(ast.parse('from ast import literal_eval as _ghost_literal_eval').body[0], include_attributes=False):
            raise ValueError('Unexpected repaired parser shape.')
        statements = statements[1:]
    if len(statements) != 1 or not isinstance(statements[0], ast.Return):
        raise ValueError('Repair supports only a direct return of eval(value).')
    ret = statements[0]
    call = ret.value
    if (not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name)
            or call.func.id != ('_ghost_literal_eval' if patched else 'eval') or call.keywords
            or len(call.args) != 1 or not isinstance(call.args[0], ast.Name) or call.args[0].id != args.args[0].arg
            or args.args[0].arg in {'eval', '_ghost_literal_eval'} or ret.lineno != ret.end_lineno):
        raise ValueError('Repair requires an unshadowed, single-line eval(value).')
    return function


def literal_parser_patch(path: str, source: str, finding_line: int) -> PatchEdit:
    function = parser_function(source)
    ret = function.body[0]
    if ret.lineno != finding_line:
        raise ValueError('Finding no longer matches the repair location. Rerun ghost find.')
    line = source.splitlines(keepends=True)[ret.lineno - 1]
    # Only a full indented return line; reject semicolons/inline function bodies.
    prefix = line[:len(line) - len(line.lstrip())]
    if not prefix or not line.lstrip().startswith('return '):
        raise ValueError('Inline parser functions are unsupported.')
    argument = function.args.args[0].arg
    newline = '\r\n' if line.endswith('\r\n') else '\n'
    new = f'{prefix}from ast import literal_eval as _ghost_literal_eval{newline}{prefix}return _ghost_literal_eval({argument})'
    if line.endswith('\n'):
        new += newline
    patched = source.replace(line, new, 1)
    parser_function(patched, patched=True)
    return PatchEdit(path=path, old=line, new=new)
