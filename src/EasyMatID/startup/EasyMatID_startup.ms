-- Linked into <userScripts>\startup. Registers the "EasyMatID" macro
-- (Customize > Toolbars, category EasyMatID). The tool itself lives in <userScripts>\EasyMatID.
macroScript EasyMatID category:"EasyMatID" buttonText:"Mat ID" tooltip:"Easy Mat ID Assigner"
(
    on execute do (
        local root = getDir #userScripts + "\\EasyMatID"
        python.Execute ("import sys\nr = r'" + root + "'\nif r not in sys.path: sys.path.insert(0, r)\nimport easy_mat_id\neasy_mat_id.show()")
    )
)
