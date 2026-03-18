import subprocess

def stage_compile():
    return subprocess.run(["python", "-m", "compileall", "src"]).returncode == 0

def stage_pytest():
    return subprocess.run(["pytest"]).returncode == 0

def stage_import(strategy_name):
    try:
        __import__(f"src.strategies.{strategy_name}.runner")
        return True
    except:
        return False

def run_all_stages(strategy_name, spec):
    return [
        {"name": "compile", "passed": stage_compile()},
        {"name": "pytest", "passed": stage_pytest()},
        {"name": "import", "passed": stage_import(strategy_name)},
    ]
