import setuptools

# read the contents of your README file
from os import path
from skodaconnect.__version__ import __version__ as lib_version
this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

def local_scheme(version):
    return ""

setuptools.setup(
    name='skodaconnect',
    version=lib_version,
    description='Communicate with Skoda Connect',
    author='lendy007',
    author_email='lendik@gmail.com',
    url='https://github.com/lendy007/skodaconnect',
    long_description=long_description,
    long_description_content_type='text/markdown',
    packages=setuptools.find_packages(),
    provides=["skodaconnect"],
    install_requires=list(open("requirements.txt").read().strip().split("\n")),
    #use_scm_version=True,
    use_scm_version={"local_scheme": local_scheme},
    setup_requires=[
        'setuptools_scm',
    ]
)
