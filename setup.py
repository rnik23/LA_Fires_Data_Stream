from setuptools import setup, find_packages

setup(
    name="lafires",
    version="0.1.0",
    packages=find_packages(),

    # ← Add this block:
    entry_points={
        "console_scripts": [
            # `lafires-demo` will invoke lafires.__main__.main()
            "lafires-demo = lafires.__main__:main",
        ],
    },
)
