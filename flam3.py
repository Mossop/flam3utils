#!/usr/bin/python

import subprocess, os, sys, re
from datetime import datetime
from xml.dom.minidom import parse, parseString
from ConfigParser import RawConfigParser as ConfigParser

OPTIONS = ["qs", "ss", "pixel_aspect", "format", "bpc", "bits", "transparency"]
DEFAULTS = "default"

def time_delta_str(delta):
  def delta_part_str(count, noun):
    if count == 0:
      return ""
    if count > 1:
      return "%d %ss " % (count, noun)
    return "1 %s " % noun

  result = ""
  seconds = delta.seconds
  hours = seconds / 3600
  seconds -= hours * 3600
  minutes = seconds / 60
  seconds -= minutes * 60

  result += delta_part_str(delta.days, "day")
  result += delta_part_str(hours, "hour")
  result += delta_part_str(minutes, "minute")
  result += delta_part_str(seconds, "second")

  return result

class ConsoleDisplay:
  filename = None
  starttime = None
  progresswidth = 50

  def startDisplay(self, filename):
    self.starttime = datetime.now()
    self.filename = filename
    sys.stdout.write("%s: 1/1 [" % filename)
    for i in range(self.progresswidth):
      sys.stdout.write(" ")
    sys.stdout.write("]")

  def redraw(self, process):
    progress = (100 * (process.strip - 1) / process.strips)
    progress += process.progress / process.strips
    sys.stdout.write("\r%s: %d/%d [" % (self.filename, process.strip, process.strips))
    count = int(self.progresswidth * progress / 100)
    for i in range(count):
      sys.stdout.write("#")
    for i in range(count, self.progresswidth):
      sys.stdout.write(" ")
    sys.stdout.write("] %5.1f%%" % process.progress)

  def endDisplay(self):
    delta = datetime.now() - self.starttime
    donetime = time_delta_str(delta)
    sys.stdout.write("\r%s: complete in %s" % (self.filename, donetime))
    for i in range(len(donetime), self.progresswidth + 1):
      sys.stdout.write(" ")
    sys.stdout.write("\n")

class Flam3Renderer:
  options = None
  executable = None
  process = None
  strip = None
  strips = None
  progress = None

  def __init__(self, options):
    self.options = options
    for path in os.environ["PATH"].split(os.pathsep):
      if os.path.isfile(os.path.join(path, "flam3-render")):
        self.executable = os.path.join(path, "flam3-render")

  def open(self, outputfile, display):
    self.progress = 0
    self.strip = 1
    self.strips = 1
    self.display = display

    environment = { }
    for option in OPTIONS:
      value = getattr(self.options, option)
      if value is not None:
        environment[option] = str(value)
    environment["out"] = outputfile
    args = [self.executable]
    self.process = subprocess.Popen(args, env=environment, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return self.process.stdin

  def _parseLine(self, line):
    if len(line) == 0:
      return

    match = re.match("strip = (\\d+)/(\\d+)", line)
    if match is not None:
      self.strip = int(match.group(1))
      self.strips = int(match.group(2))
      self.progress = 0
      self.display.redraw(self)
      return

    match = re.match("chaos:\\s+(?:(\\d+\\.\\d)%)?", line)
    if match is not None:
      if match.group(1) is not None:
        self.progress = float(match.group(1))
      else:
        self.progress = 0
      self.display.redraw(self)
      return

    match = re.match("density estimation: ", line)
    if match is not None:
      return

    if line.startswith("filtering..."):
      return
    if line.startswith("writing "):
      return
    if line.startswith("done."):
      return
    if line.startswith("total time ="):
      return

    print line

  def wait(self):
    line = ""
    str = self.process.stdout.read(1)
    while len(str) > 0:
      if str == "\n" or str == "\r":
        self._parseLine(line)
        line = ""
      else:
        line += str
        if len(line) > 3 and line[-3:] == "...":
          self._parseLine(line)
          line = ""
      str = self.process.stdout.read(1)

class Flame:
  document = None
  element = None

  def __init__(self, element):
    self.element = element.cloneNode(True)
    self.document = parseString("<flames/>")
    self.document.documentElement.appendChild(self.element)

  def render(self, filename, options):
    if options.height is not None or options.width is not None:
      (width, height) = self.element.getAttribute("size").split(" ")
      width = int(width)
      height = int(height)
      scale = float(self.element.getAttribute("scale"))

      if options.height is None:
        newwidth = int(options.width)
        ratio = float(newwidth) / width
        newheight = int(height * ratio)
      elif options.width is None:
        newheight = int(options.height)
        ratio = float(newheight) / height
        newwidth = int(width * ratio)
      else:
        newheight = int(options.height)
        newwidth = int(options.width)
        if options.fix is not None:
          scaleheight = options.fix == "height"
        else:
          scaleheight = (float(newwidth) / newheight) > (float(width) / height)

        if scaleheight:
          ratio = float(newheight) / height
          if options.keepratio:
            newwidth = int(width * ratio)
        else:
          ratio = float(newwidth) / width
          if options.keepratio:
            newheight = int(height * ratio)

      scale = scale * ratio
      self.element.setAttribute("size", "%d %d" % (newwidth, newheight))
      self.element.setAttribute("scale", "%f" % scale)

    renderer = Flam3Renderer(options)
    display = ConsoleDisplay()
    display.startDisplay(filename)
    stream = renderer.open(filename, display)
    self.document.writexml(stream, "  ", "  ")
    stream.close()
    renderer.wait()
    display.endDisplay()

class Flam3File:
  basename = None
  filename = None
  flames = None

  def __init__(self, filename):
    self.filename = filename
    (self.basename, dummy) = os.path.splitext(self.filename)
    doc = parse(self.filename)
    elements = doc.getElementsByTagName("flame")
    self.flames = [Flame(e) for e in elements]

def load_config(options):
  configfile = os.path.expanduser(options.configfile)
  if not os.path.isfile(configfile):
    return
  config = options.config
  parser = ConfigParser()
  parser.read(configfile)

  if config is not None:
    hasconfig = parser.has_section(config)
  else:
    hasconfig = False

  if parser.has_section(DEFAULTS):
    for key in parser.options(DEFAULTS):
      if hasconfig and parser.has_option(config, key):
        continue
      if getattr(options, key) is None:
        setattr(options, key, parser.get(DEFAULTS, key))

  if not hasconfig:
    return
  for key in parser.options(config):
    if getattr(options, key) is None:
      setattr(options, key, parser.get(config, key))

def main():
  from optparse import OptionParser
  parser = OptionParser()
  parser.add_option("", "--qs", dest = "qs", type = "int",
                    help="quality scale")
  parser.add_option("", "--ss", dest = "ss", type = "int",
                    help="size scale")
  parser.add_option("", "--transparency", dest = "transparency",
                    action = "store_const", const = 1,
                    help="make background transparent if the image format supports it")
  parser.add_option("", "--pixel_aspect", dest = "pixel_aspect", type = "int",
                    metavar = "ASPECT",
                    help="pixel aspect ratio")
  parser.add_option("", "--bits", dest = "bits", type = "int",
                    metavar = "BITS",
                    help="size of internal buffers")
  parser.add_option("", "--bpc", dest = "bpc", type = "int",
                    metavar = "BITS",
                    help="bits per colour channel")
  parser.add_option("", "--format", dest = "format", type = "choice",
                    choices = ("png", "jpg", "ppm"),
                    help="output image format")
  parser.add_option("", "--height", dest = "height", type = "int",
                    help="output height")
  parser.add_option("", "--width", dest = "width", type = "int",
                    help="output width")
  parser.add_option("", "--keepratio", dest = "keepratio",
                    action = "store_true",
                    help="maintains output aspect ratio when providing both width and height")
  parser.add_option("", "--fix", dest = "fix", type = "choice",
                    choices = ("width", "height"), metavar = "<width|height>",
                    help="when resizing fix the image width or height and crop or expand the other")
  parser.add_option("", "--config", dest = "config",
                    help="configuration settings to use as defaults")
  parser.add_option("", "--configfile", dest = "configfile",
                    default = "~/.flam3.ini", metavar = "FILE",
                    help="file to load configuration settings from, defaults to ~/.flam3.ini")
  parser.usage = "%prog [options] <file1> <file2> ... <filen>"
  (options, args) = parser.parse_args()
  if (len(args) == 0):
    parser.print_usage()

  load_config(options)

  if options.format is None:
    options.format = "png"

  if options.height is not None or options.width is not None:
    options.ss = None

  flamefiles = []
  for file in args:
    if not os.path.isfile(file):
      print("File %s not found." % file)
      parser.print_usage()
      return
    flamefiles.append(Flam3File(file))

  for flamefile in flamefiles:
    pos = 0
    for flame in flamefile.flames:
      pos += 1
      if len(flamefile.flames) > 1:
        output = "%s%03d.%s" % (flamefile.basename, pos, options.format)
      else:
        output = "%s.%s" % (flamefile.basename, options.format)
      flame.render(output, options)

if __name__ == "__main__":
  main()
