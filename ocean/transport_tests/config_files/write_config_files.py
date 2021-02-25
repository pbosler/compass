#!/usr/bin/env python3
"""
Sets up config files for the transport_tests
"""

import os
import argparse
from yaml import safe_load
from shutil import rmtree, copy
from sys import exit
import glob
from datetime import timedelta


# Define common paths
script_path = os.path.dirname(os.path.realpath(__file__))
compass_root = os.path.normpath(os.path.join(script_path, '..', '..', '..'))
compass_parent = os.path.normpath(os.path.join(compass_root, '..'))
transport_tests_dir = os.path.abspath(os.path.join(script_path, '..'))
template_dir = os.path.abspath(os.path.join(transport_tests_dir,'templates'))

# Config files
xmlin = glob.glob(os.path.join(script_path,"*.xml.in"))
xmlcp = glob.glob(os.path.join(script_path, "*.xml"))

# Define common strings
shebang = r'#!/usr/bin/env python'
cblock = '"""\n'
qstr = '"'
gen_block = cblock + "This script was autogenerated by {}\n".format(
  os.path.relpath(__file__,start=compass_parent)) + cblock

# Define all test cases
all_resvals = [60,90,120,150,180,210,240]
all_test_names = ["correlated_tracers", "deformation3D", "divergent2D", "Hadley3D",
  "horizontalWithTopo3D", "nondivergent2D", "rotation2D"]

#---------------------------------------------------
#
#   Module functions
#
#---------------------------------------------------

def print_path_info():
  """
    Print the common paths used by this script
  """
  print("compass_root = ", compass_root)
  print("script_path =  ", script_path)

def is_res_dir(path):
  """
    Returns true if path corresponds to a resolution directory, e.g., QU240
  """
  return os.path.isdir(path) and path[:2] == 'QU'

def write_base_mesh_script(floc,res):
  """
    Writes the mpas script, build_base_mesh.py, that defines the base mesh file for a given test
    to path=floc for a quasi-uniform resolution defined by res.
  """
  desc_block = cblock + """build_base_mesh.py\n
    % Create cell width array for this mesh on a regular latitude-longitude grid.
    % Outputs:
    %    cellWidth - m x n array, entries are desired cell width in km
    %    lat - latitude, vector of length m, with entries between -90 and 90, degrees
    %    lon - longitude, vector of length n, with entries between -180 and 180, degrees\n""" + cblock

  import_block = """import numpy as np
from mpas_tools.ocean import build_spherical_mesh"""
  cell_width_fn = """def cellWidthVsLatLon():
    ddeg = 10
    constantCellWidth = {}

    lat = np.arange(-90, 90.01, ddeg)
    lon = np.arange(-180, 180.01, ddeg)

    cellWidth = constantCellWidth * np.ones((lat.size, lon.size))
    return cellWidth, lon, lat""".format(res)

  main_fn = """if __name__ == '__main__':
    cellWidth, lon, lat = cellWidthVsLatLon()
    build_spherical_mesh(cellWidth, lon, lat, out_filename='base_mesh.nc')"""

  fpath = os.path.join(floc,'build_base_mesh.py')
  with open(os.open(fpath, os.O_CREAT | os.O_WRONLY, 0o775 ), 'w') as f:
    f.write(shebang + "\n")
    f.write(gen_block)
    f.write(desc_block)
    f.write(import_block + "\n\n")
    f.write(cell_width_fn + "\n\n")
    f.write(main_fn + "\n")

def get_input_dict(fname):
  """
    Reads configuration input yaml file, returns a dictionary
  """
  if not fname.endswith('.yaml'):
    raise RuntimeError("config input expects a .yaml file.")
  with open(fname,'r') as f:
    cfg = safe_load(f)
  return cfg

def clean_transport_tests():
  """
    Removes all previously confifgured test cases
  """
  script_path = os.path.dirname(os.path.realpath(__file__))
  transport_tests_dir = os.path.abspath(os.path.join(script_path, '..'))
  os.chdir(transport_tests_dir)
  for d in sorted(os.listdir()):
    if is_res_dir(d):
      rmtree(d);

def verify_cfg_input(cfg):
  """
    Verify yaml input for correct values
  """
  if not (cfg["integrator"] == "RK4" or cfg["integrator"] == "split_explicit"):
    raise RuntimeError("Integrator must be one of ['RK4', 'split_explicit']")
  for reskey in cfg["resolutions"]:
    resval = int(reskey[2:])
    if reskey[:2] != "QU":
      raise NotImplementedError("transport tests for grids other than quasi-uniform are not implemented.")
    if resval <= 0:
      raise RuntimeError("Unexpected resolution value")
    if float(cfg["resolutions"][reskey]["timestep_minutes"]) <= 0:
      raise RuntimeError("Invalid time step value")
    if int(cfg["resolutions"][reskey]["vert_levels"]) <= 0:
      raise RuntimeError("Invalid number of vertical levels")
    if int(cfg["resolutions"][reskey]["nprocs"]) <= 0:
      raise RuntimeError("Invalid number of processors")

def get_timestep_str(dtminutes):
   """
    These tests expect the time step to be input in units of minutes, but MPAS
    requires an "HH:MM:SS" string.  This function converts the time step input
    into the formatted string used by MPAS.
   """
   dt = timedelta(minutes=dtminutes)
   if  dtminutes < 1:
     dtstr = "00:00:" + str(dt.total_seconds())[:2]
   elif dtminutes >= 60:
     dthours = dt/timedelta(hours=1)
     dt = dt - timedelta(hours=int(dthours))
     dtminutes = dt/timedelta(minutes=1)
     dt = dt - timedelta(minutes=int(dtminutes))
     dtstr = str(int(dthours))[:2].zfill(2) + ":" + str(int(dtminutes))[:2].zfill(2) +\
     ":"+str(int(dt.total_seconds()))[:2].zfill(2)
   else:
     dtminutes = dt/timedelta(minutes=1)
     dtstr = "00:" + str(int(dtminutes))[:2].zfill(2) + ":00"
   return dtstr

def get_sed_exp(dt, nprocs, integrator):
  """
    Some of the required MPAS input are defined in template .xml files.
    The templates need to be altered with correct values (from input) to
    generate MPAS-readable input files.

    This function generates the sed commands required to modify the templates
    according to the config input.
  """
  dts = r"s/TMP_config_dt/" + get_timestep_str(dt) + "/g"
  nps = r"s/TMP_procs/" + str(nprocs) + "/g"
  tis = r"s/TMP_integrator/" + integrator + "/g"
  return r"{} ; {} ; {}".format(dts,nps,tis)

#---------------------------------------------------
#
#   Main
#
#---------------------------------------------------
if __name__ == '__main__':
  print_path_info()

  # Define input args
  parser = argparse.ArgumentParser(description="MPAS-Ocean Transport Tests configuration utility")
  parser.add_argument("-i", "--input_file", nargs='?', default="config_input.yaml",
    help="configuration file for transport test resolutions, time integrators. Default: config_input.yaml")
  parser.add_argument("--clean", action="store_true",
    help="completely remove an existing set of transport tests' configuration files (does not touch test data).")
  parser.add_argument("--all", action="store_true",
    help="enable all transport tests (this ignores the input file)")

  # Process input args
  args = parser.parse_args()

  if args.clean:
    # Clean all test cases and exit
    print("cleaning all transport tests from " + transport_tests_dir)
    clean_transport_tests()
    exit(0)
  elif args.all:
    raise NotImplementedError("Make all tests not implemented yet --- need timesteps, levels, and nprocs")
  else:
    print("reading input from file " + args.input_file)

  # Read & verify config input
  cfg = get_input_dict(args.input_file)
  print("Building transport tests for resolutions = ", cfg["resolutions"].keys())
  verify_cfg_input(cfg)
  itr = cfg["integrator"]

  # Iterate over resolutions
  ntests = 0
  print(transport_tests_dir)
  os.chdir(transport_tests_dir)
  for reskey in cfg["resolutions"]:
    resval = int(reskey[2:])
    resdir = reskey
    dt = float(cfg["resolutions"][reskey]["timestep_minutes"])
    nprocs = int(cfg["resolutions"][reskey]["nprocs"])
    nlev = int(cfg["resolutions"][reskey]["vert_levels"])
    sedin = get_sed_exp(dt, nprocs, itr)
    # Iterate over test cases
    for tc in cfg["test_names"]:
      tcdir = os.path.join(transport_tests_dir, reskey,tc)
      ntests += 1
      print("tcdir = ", tcdir)
      try:
        os.makedirs(tcdir)
        print("created test case directory: ", tcdir)
      except FileExistsError:
        print("test case directory exists: ", tcdir)
      # Write base mesh script
      write_base_mesh_script(tcdir, resval)
      for xf in xmlin:
        oldfile = os.path.split(xf)[-1]
        newfile = oldfile[:-3]
        sedstr = "sed " + "'" + sedin + "' " + xf + " > " + os.path.join(tcdir, newfile)
        os.system(sedstr)
      for xf in xmlcp:
        copy(xf, os.path.join(tcdir, os.path.split(xf)[-1]))

  print("created ", ntests, " tests")

