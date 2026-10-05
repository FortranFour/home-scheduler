"""Single-instance UI setup and import of existing YAML installations."""
try:
    import probatio as vol
except ImportError:
    import voluptuous as vol

from homeassistant import config_entries

from .const import DOMAIN, NAME


class HomeSchedulerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create one scheduler; devices and schedules are edited in its card."""

    VERSION = 1

    async def _create(self):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=NAME, data={})

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        if user_input is not None:
            return await self._create()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    async def async_step_import(self, user_input):
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        return await self._create()
