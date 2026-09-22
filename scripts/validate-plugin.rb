#!/usr/bin/env ruby
# frozen_string_literal: true
#
# Renders every layout against every sample payload with the real Liquid
# engine, inlining TRMNL's {% template %} / {% render %} extensions first.
# Fails non-zero on Liquid errors, missing expected content, or a payload
# that exceeds TRMNL's documented webhook size limit.
#
# Usage: ruby scripts/validate-plugin.rb

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

SHARED = File.read(File.join(SRC, "shared.liquid"))

def expand_markup(layout_markup)
  templates = {}
  shared_without_templates = SHARED.gsub(
    /{%\s*template\s+([A-Za-z0-9_]+)\s*%}(.*?){%\s*endtemplate\s*%}/m
  ) do
    templates[Regexp.last_match(1)] = Regexp.last_match(2)
    ""
  end

  layout_markup.gsub(/{%\s*render\s+"([A-Za-z0-9_]+)"[^%]*%}/) do
    templates.fetch(Regexp.last_match(1)) do
      raise "unknown shared template: #{Regexp.last_match(1)}"
    end
  end
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

failures = []
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
    markup = expand_markup(File.read(File.join(SRC, "#{layout}.liquid")))
    template = Liquid::Template.parse(markup)
    rendered = template.render!(trmnl_context.merge(payload))
    render_count += 1

    failures << "#{layout}/#{sample_file}: Liquid error in output" if rendered.include?("Liquid error")
    failures << "#{layout}/#{sample_file}: literal nil leaked into output" if rendered.match?(/[\s>]nil[\s<]/)

    case sample_file
    when "mixed.json"
      failures << "#{layout}/#{sample_file}: missing merchant Amazon" unless rendered.include?("Amazon")
      failures << "#{layout}/#{sample_file}: missing out-for-delivery copy" unless rendered.include?("Out for delivery")
      # Every delivery must reach the reader: a layout that silently drops a
      # status bucket is a bug, not a design choice. The quadrant is the one
      # intentional exception: it renders the single most urgent row only.
      merchants = payload["deliveries"].map { |d| d["merchant"] }
      merchants = merchants.first(1) if layout == "quadrant"
      merchants.each do |merchant|
        next if rendered.include?(merchant)

        failures << "#{layout}/#{sample_file}: delivery #{merchant} did not render"
      end
    when "singleton.json"
      failures << "#{layout}/#{sample_file}: single-item array did not render" unless rendered.include?("Amazon")
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
puts "ok: all sample payloads within #{MAX_PAYLOAD_BYTES} bytes"
