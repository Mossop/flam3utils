#!/usr/bin/python

import subprocess, os, sys, re
from xml.dom.minidom import parse, parseString

OPTIONS = ["qs", "ss", "pixel_aspect", "format"]

class ConsoleDisplay:
  filename = None

  def startDisplay(self, filename):
    self.filename = filename
    sys.stdout.write("%s: 1/1 [                                                  ]" % filename)

  def redraw(self, process):
    progress = (100 * (process.strip - 1) / process.strips)
    progress += process.progress / process.strips
    sys.stdout.write("\r%s: %d/%d [" % (self.filename, process.strip, process.strips))
    count = int(progress / 2)
    for i in range(count):
      sys.stdout.write("#")
    for i in range(count, 50):
      sys.stdout.write(" ")
    sys.stdout.write("] %5.1f" % process.progress)

  def endDisplay(self):
    print ""

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

    env = { }
    for opt in OPTIONS:
      env[opt] = str(getattr(self.options, opt))
    env["out"] = outputfile
    args = [self.executable]
    self.process = subprocess.Popen(args, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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
        newwidth = options.width
        ratio = float(newwidth) / width
        newheight = int(height * ratio)
      elif options.width is None:
        newheight = options.height
        ratio = float(newheight) / height
        newwidth = int(width * ratio)
      else:
        newheight = options.height
        newwidth = options.width
        if options.fix is not None:
          scaleheight = options.fix == "height"
        else:
          scaleheight = (float(newwidth) / newheight) > (float(width) / height)

        if scaleheight:
          ratio = float(newheight) / height
          if options.maintainratio:
            newwidth = int(width * ratio)
        else:
          ratio = float(newwidth) / width
          if options.maintainratio:
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

def main():
  from optparse import OptionParser
  parser = OptionParser()
  parser.add_option("", "--qs", dest = "qs", type = "int", default = 1,
                    help="quality scale")
  parser.add_option("", "--ss", dest = "ss", type = "int", default = 1,
                    help="size scale")
  parser.add_option("-a", "--aspect", dest = "pixel_aspect", type = "int", default = 1,
                    help="pixel aspect ratio")
  parser.add_option("-f", "--format", dest = "format", default = "png",
                    help="output image format")
  parser.add_option("", "--height", dest = "height", type = "int",
                    help="output height")
  parser.add_option("", "--width", dest = "width", type = "int",
                    help="output width")
  parser.add_option("-r", "--keepratio", dest = "maintainratio", action = "store_true", default = False,
                    help="maintains output aspect ratio when providing both width and height")
  parser.add_option("", "--fix", dest = "fix", metavar = "<width|height>",
                    help="when resizing fix the image width or height and crop or expand the other")
  parser.usage = "%prog [options] <file1> <file2> ... <filen>"
  (options, args) = parser.parse_args()
  if (len(args) == 0):
    parser.print_usage()
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
      if len(flamefile.flames) > 0:
        output = "%s%03d.%s" % (flamefile.basename, pos, options.format)
      else:
        output = "%s.%s" % (flamefile.basename, options.format)
      flame.render(output, options)

if __name__ == "__main__":
  main()
