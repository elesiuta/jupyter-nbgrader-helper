import setuptools
import nbhelper

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="nbhelper",
    version=nbhelper.VERSION,
    description="A collection of helpful functions for use with jupyter nbgrader",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/elesiuta/jupyter-nbgrader-helper",
    py_modules=['nbhelper'],
    entry_points={
        'console_scripts': [
            'nbhelper = nbhelper:main'
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Framework :: Jupyter",
        "Intended Audience :: Education",
        "Operating System :: OS Independent",
    ],
)
