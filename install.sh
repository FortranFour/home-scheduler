#!/bin/sh
# Optional package/compatibility installer; configuration.yaml is never edited.
set -eu
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
config_dir=${1:-/config}
if [ ! -d "$config_dir" ] || [ ! -f "$config_dir/configuration.yaml" ]; then
  printf '%s\n' "Expected a Home Assistant configuration directory containing configuration.yaml: $config_dir" >&2
  exit 1
fi
config_dir=$(CDPATH= cd -- "$config_dir" && pwd)
component_dir="$config_dir/custom_components/home_scheduler"
frontend_dir="$config_dir/www/home-scheduler"
package_file="$config_dir/packages/home_scheduler.yaml"
had_model_index=0
if [ -f "$frontend_dir/models.json" ]; then had_model_index=1; fi
backup_dir="$config_dir/home_scheduler_backups/$(date +%Y%m%d_%H%M%S)_$$"
for source_file in custom_components/home_scheduler/__init__.py custom_components/home_scheduler/frontend/demo-home.glb packages/home_scheduler.yaml; do
  if [ ! -f "$source_dir/$source_file" ]; then
    printf '%s\n' "Incomplete extracted package: missing $source_file" >&2
    exit 1
  fi
done
if [ -e "$component_dir" ] || [ -e "$frontend_dir" ] || [ -e "$package_file" ]; then
  mkdir -p "$backup_dir"
  if [ -e "$component_dir" ]; then cp -R "$component_dir" "$backup_dir/component"; fi
  if [ -e "$frontend_dir" ]; then cp -R "$frontend_dir" "$backup_dir/frontend"; fi
  if [ -e "$package_file" ]; then cp "$package_file" "$backup_dir/package.yaml"; fi
  printf '%s\n' "Previous Home Scheduler files backed up to $backup_dir"
fi
mkdir -p "$component_dir" "$frontend_dir" "$config_dir/packages"
cp -R "$source_dir/custom_components/home_scheduler/." "$component_dir/"
for asset_file in "$source_dir/custom_components/home_scheduler/frontend/"*; do
  # The bundled empty index must not replace a user's existing model list.
  if [ "${asset_file##*/}" = models.json ] && [ "$had_model_index" -eq 1 ]; then continue; fi
  cp -R "$asset_file" "$frontend_dir/"
done
if [ ! -e "$package_file" ]; then
  cp "$source_dir/packages/home_scheduler.yaml" "$package_file"
else
  printf '%s\n' "Existing packages/home_scheduler.yaml retained, including your helpers and startup automations."
fi
# A personal preset stays separate from the distributable demo package.
for preset_file in "$config_dir/home_scheduler_my_house.json" "$source_dir/home_scheduler_my_house.json"; do
  if [ -f "$preset_file" ]; then
    cp "$preset_file" "$frontend_dir/my-house.json"
    break
  fi
done
if [ -f "$frontend_dir/my-house.json" ] && [ "$had_model_index" -eq 0 ]; then
  printf '%s\n' '{"models":[{"id":"my-house","name":"My house","url":"/local/home-scheduler/my-house.json"}]}' > "$frontend_dir/models.json"
fi
if [ -f "$frontend_dir/my-house.json" ] && [ "$had_model_index" -eq 1 ]; then
  printf '%s\n' "Existing model index retained; import any additional personal preset through Import configuration."
fi
printf '%s\n' \
  "Installed Home Scheduler & Simulator 0.4.1." \
  "Use your existing packages: include; configuration.yaml was not changed." \
  "With packages enabled, YAML setup imports the integration entry automatically." \
  "Check configuration, restart Home Assistant, then add home_scheduler_view.yaml as a new dashboard view." \
  "The integration registers the scheduler card; remove any old scheduler module/resource entry." \
  "The 3D view requires floor3dx-card 1.4.0 or later." \
  "Select a home in the Model menu to populate device rows and bindings automatically." \
  "Demo devices are unlinked and Physical devices starts off."
