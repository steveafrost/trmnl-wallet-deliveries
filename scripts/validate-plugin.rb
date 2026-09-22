#!/usr/bin/env ruby
# frozen_string_literal: true
#
# Renders every layout against every sample payload with the real Liquid
# engine, inlining TRMNL's {% template %} / {% render %} extensions first
# (render arguments become assignments, the way the engine binds them).
# Fails non-zero on Liquid errors, missing expected content, duplicate
# merchants, or a payload over TRMNL's documented webhook size limit.
#
# Usage: ruby scripts/validate-plugin.rb [--emit-build <trmnlp-build-dir>]

require "json"

begin
  require "liquid"
rescue LoadError
  warn "Missing Ruby gem: liquid"
  warn "Install with: gem install --user-install liquid"
  exit 2
end

ROOT = File.expand_path("..", __dir__)
SRC = File.join(ROOT, "src")
SAMPLES_DIR = File.join(ROOT, "samples")
LAYOUTS = %w[full half_horizontal half_vertical quadrant].freeze
PAYLOAD_LIMIT_BYTES = 2048
MAX_PAYLOAD_BYTES = 5_120 # TRMNL+ ceiling, the hard stop for the sender

# With --emit-build <dir>, the mixed sample's render is spliced into the CSS
# shell that `trmnlp build` writes into <dir>, so the result can be screenshotted
# at panel size for the recipe images. `trmnlp build` alone ships no data.
EMIT_DIR = ARGV.include?("--emit-build") ? ARGV[ARGV.index("--emit-build") + 1] : nil

SHARED = File.read(File.join(SRC, "shared.liquid"))
RENDER = /{%\s*render\s+"([A-Za-z0-9_]+)"\s*(?:,\s*(.*?))?\s*%}/m

def template_bodies
  bodies = {}
  SHARED.gsub(/{%\s*template\s+([A-Za-z0-9_]+)\s*%}(.*?){%\s*endtemplate\s*%}/m) do
    bodies[Regexp.last_match(1)] = Regexp.last_match(2)
    ""
  end
  bodies
end

def render_args(source)
  source.scan(RENDER).map { |name, args| [name, args.to_s] }
end

def param_pairs(args)
  args.scan(/([A-Za-z0-9_]+)\s*:\s*(".*?"|[^,]+)/m)
end

# Root identifiers of a Liquid expression: `a.b | filter: c` -> [a, c].
# String literals are stripped first so their words are never mistaken for
# variables, and a filter's own name is skipped - only its arguments count.
def expression_roots(expr)
  cleaned = expr.gsub(/"[^"]*"|'[^']*'/, " ")
  segments = cleaned.split("|")
  roots = segments.first.to_s.scan(/\b([a-z_][A-Za-z0-9_]*)\b/).flatten
  segments.drop(1).each do |segment|
    args = segment.split(":", 2)[1]
    # Only the part before a dot is a root: `e.merchant` reads `e`, and
    # `forloop.index0` reads `forloop`. Without the lookbehind the property name
    # looks like a variable of its own, so any template using `forloop.index`
    # reports a false scope failure.
    roots.concat(args.to_s.scan(/(?<!\.)\b([a-z_][A-Za-z0-9_]*)\b/).flatten) if args
  end
  roots.reject { |word| %w[and or contains eq ne gt lt ge le].include?(word) }
end

# Everything a template body references, split into what it declares itself
# (assigns, loop variables, its own render arguments) and the roots it reads.
def scan_references(body)
  locals = []
  roots = []
  body.scan(/{%\s*assign\s+([A-Za-z0-9_]+)\s*=\s*(.*?)%}/m) do |var, expr|
    locals << var
    roots.concat(expression_roots(expr))
  end
  body.scan(/{%\s*for\s+([A-Za-z0-9_]+)\s+in\s+(.*?)%}/m) do |var, expr|
    locals << var
    roots.concat(expression_roots(expr))
  end
  body.scan(/{%\s*(?:if|elsif|unless)\s+(.*?)%}/m) { |cond| roots.concat(expression_roots(cond.first)) }
  body.scan(/{{(.*?)}}/m) { |expr| roots.concat(expression_roots(expr.first)) }
  body.scan(RENDER) do |_template, args|
    param_pairs(args.to_s).each do |key, value|
      locals << key
      roots.concat(expression_roots(value))
    end
  end
  [locals, roots]
end

# TRMNL renders templates with Shopify's Liquid, where {% render %} has an
# isolated scope: a template sees only the arguments its call passes. A layout
# variable that a template reads without it being passed is nil at runtime -
# which shows up as a silently empty section, not an error. So check every call
# site: it must pass everything the template needs.
def scope_failures(bodies, layouts)
  required = bodies.to_h do |name, body|
    locals, roots = scan_references(body)
    [name, (roots - locals - %w[trmnl empty nil true false forloop]).uniq]
  end

  layouts.merge(bodies).flat_map do |owner, source|
    render_args(source).flat_map do |name, args|
      params = param_pairs(args).map(&:first)
      (required[name] - params).map do |root|
        "#{owner} renders #{name} without passing #{root} (template scopes are isolated, so it would be nil)"
      end
    end
  end
end

# Inline {% render "x", k: v %} as {% assign k = v %} followed by x's body,
# repeating until no renders remain so templates can render templates.
def expand_markup(layout_markup)
  templates = template_bodies

  markup = layout_markup
  6.times do
    break unless markup.match?(RENDER)

    markup = markup.gsub(RENDER) do
      name = Regexp.last_match(1)
      args = Regexp.last_match(2).to_s
      body = templates.fetch(name) { raise "unknown shared template: #{name}" }
      assigns = param_pairs(args).map do |key, value|
        "{% assign #{key} = #{value.strip} %}"
      end.join
      "#{assigns}#{body}"
    end
  end
  markup
end

def trmnl_context
  {
    "trmnl" => {
      "plugin_settings" => {
        "custom_fields_values" => {
          "title" => "Deliveries",
          "show_carrier" => "yes",
          "show_tracking" => "no",
          "hide_delivered" => "no",
          "max_items" => "8"
        }
      },
      "user" => { "locale" => "en" }
    }
  }
end

def sample_files
  Dir.children(SAMPLES_DIR).select { |f| f.end_with?(".json") }.sort
end

layout_sources = LAYOUTS.to_h { |name| [name, File.read(File.join(SRC, "#{name}.liquid"))] }
failures = scope_failures(template_bodies, layout_sources)
render_count = 0

sample_files.each do |sample_file|
  raw = File.read(File.join(SAMPLES_DIR, sample_file))
  payload = JSON.parse(raw)

  if raw.bytesize > MAX_PAYLOAD_BYTES
    failures << "#{sample_file} is #{raw.bytesize} bytes, over the hard webhook ceiling"
  end
  if raw.bytesize > PAYLOAD_LIMIT_BYTES
    warn "note: #{sample_file} is #{raw.bytesize} bytes (over #{PAYLOAD_LIMIT_BYTES}; only ok on TRMNL+)"
  end

  LAYOUTS.each do |layout|
    markup = expand_markup(layout_sources[layout])
    template = Liquid::Template.parse(markup)
    rendered = template.render!(trmnl_context.merge(payload))
    render_count += 1

    failures << "#{layout}/#{sample_file}: Liquid error in output" if rendered.include?("Liquid error")
    failures << "#{layout}/#{sample_file}: literal nil leaked into output" if rendered.match?(/[\s>]nil[\s<]/)

    if EMIT_DIR && sample_file == "mixed.json"
      shell_path = File.join(EMIT_DIR, "#{layout}.html")
      if File.exist?(shell_path)
        shell = File.read(shell_path)
        view_open = shell[/<div class="view view--[^"]*">/]
        unless view_open
          failures << "#{shell_path}: no .view container to fill"
          next
        end
        # `trmnlp build` renders the markup with no merge variables at all, so the
        # shell carries a no-data render. Keep the shell's head and view tag, drop
        # its body, and close the same two wrappers the shell had.
        head = shell[0, shell.index(view_open) + view_open.length]
        File.write(shell_path, "#{head}\n#{rendered}\n      </div>\n    </div>\n  </body>\n</html>\n")
        puts "filled #{shell_path} with #{sample_file}"
      else
        failures << "#{shell_path} missing (run: trmnlp build)"
      end
    end

    case sample_file
    when "mixed.json"
      failures << "#{layout}/#{sample_file}: missing merchant Amazon" unless rendered.include?("Amazon")
      failures << "#{layout}/#{sample_file}: missing out-for-delivery copy" unless rendered.include?("Out for delivery")
      failures << "#{layout}/#{sample_file}: missing delayed copy" unless rendered.include?("Delayed")
      # show_tracking is off in the validator's context, so a tracking number in
      # the output means a layout ignored the field. Read the value from the
      # sample rather than hardcoding it, so this file carries no data literals.
      tracking = payload["events"].map { |e| e["tracking"].to_s }.reject(&:empty?).first
      if tracking && rendered.include?(tracking)
        failures << "#{layout}/#{sample_file}: tracking number shown while show_tracking is off"
      end

      # The stream carries history, so the same merchant appears twice. Only the
      # newest event may render - a stale row is a bug, not a design choice.
      if rendered.scan("Amazon").size > 1
        failures << "#{layout}/#{sample_file}: stale Amazon event rendered alongside the newest one"
      end

      # Every delivery must reach the reader: a layout that silently drops a
      # status bucket is a bug. The quadrant is the intentional exception - it
      # shows the two most urgent rows only.
      merchants = payload["events"].map { |e| e["merchant"] }.uniq
      merchants = %w[Home Depot Amazon] if layout == "quadrant"
      merchants.each do |merchant|
        next if rendered.include?(merchant)

        failures << "#{layout}/#{sample_file}: delivery #{merchant} did not render"
      end
    when "singleton.json"
      failures << "#{layout}/#{sample_file}: single-item stream did not render" unless rendered.include?("Amazon")
    when "noise.json"
      # A shortcut run with no notification input posts an event with every field
      # empty. It must be ignored, not rendered as a generic "Package — Update" row.
      failures << "#{layout}/#{sample_file}: the real event did not render" unless rendered.include?("Amazon")
      failures << "#{layout}/#{sample_file}: an empty event rendered a row" if rendered.include?("Package") || rendered.include?("Update")
    when "empty.json"
      failures << "#{layout}/#{sample_file}: missing empty state" unless rendered.include?("Nothing in flight")
    end
  rescue StandardError => e
    failures << "#{layout}/#{sample_file}: #{e.class}: #{e.message}"
  end
end

if failures.any?
  warn failures.join("\n")
  exit 1
end

puts "ok: #{render_count} layout/sample renders clean (#{LAYOUTS.length} layouts x #{sample_files.length} samples)"
puts "ok: template scope lint found no unpassed variables"
puts "ok: all sample payloads within #{MAX_PAYLOAD_BYTES} bytes"
