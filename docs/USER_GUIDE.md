# User Guide - Intelligent Heating Pilot

## Welcome to IHP!

**Intelligent Heating Pilot (IHP)** is a smart heating assistant for Home Assistant that learns how your heating system works and automatically starts heating at exactly the right time.

### What IHP Does

Instead of manually deciding when to turn on heating, IHP:

- ✅ **Learns** how fast your room heats
- ✅ **Calculates** the optimal start time
- ✅ **Triggers** heating automatically
- ✅ **Improves** predictions with each cycle

### What IHP Doesn't Do (Yet)

These features are planned for future versions:
- Setback optimization (deciding when to lower temperature)
- Occupancy-aware scheduling
- Multi-zone coordination
- Energy cost optimization

---

## 🚀 Quick Start (15 minutes)

### 1. Install IHP
Follow [Installation Guide](INSTALLATION.md)

### 2. Configure IHP  
Follow [Configuration Guide](CONFIGURATION.md)

### 3. Learn How It Works
Read [How IHP Works](HOW_IT_WORKS.md) to understand:
- What learned heating slope is
- How heating cycles are detected
- How predictions are calculated

### 4. Monitor & Troubleshoot
Check [Troubleshooting Guide](TROUBLESHOOTING.md) if anything seems wrong

---

## 📚 Documentation Overview

| Document | For Whom | Read This If... |
|----------|----------|-----------------|
| **[Installation](INSTALLATION.md)** | First-time users | You need to install IHP |
| **[Configuration](CONFIGURATION.md)** | Setup users | You're setting up IHP for the first time |
| **[How It Works](HOW_IT_WORKS.md)** | Curious users | You want to understand what's happening behind the scenes |
| **[Troubleshooting](TROUBLESHOOTING.md)** | Users with issues | Something isn't working right |

---

## 🎯 Common Tasks

### Task: Verify IHP is working

**Steps:**
1. Go to Settings → Devices & Services
2. Find "Intelligent Heating Pilot"
3. Click on it to see the device
4. Should show several sensors with values
5. If no sensors, see [Troubleshooting](TROUBLESHOOTING.md)

### Task: Check what IHP learned

**Steps:**
1. Find your IHP device
2. Look for "Learned Heating Slope" sensor
3. Value should be between 0.5-5.0 (°C per hour)
4. If 0 or 99.9, IHP is still learning (wait 1-2 more cycles)

### Task: See next heating plan

**Steps:**
1. Find your IHP device  
2. Look for "Anticipation Time" sensor
3. Shows when IHP will trigger heating next

### Task: Change configuration

**Steps:**
1. Settings → Devices & Services
2. Find your Intelligent Heating Pilot
3. Click ⋮ (three dots) menu
4. Select "Reconfigure"
5. Update entities, click Submit
6. Integration reloads automatically

---

## 💡 Tips & Best Practices

### ✅ Do This

- ✅ Let IHP run for 5-10 heating cycles before judging accuracy
- ✅ Monitor the "Learned Heating Slope" sensor (should stabilize)
- ✅ Check logs if behavior seems strange

### ❌ Don't Do This

- ❌ Don't disable scheduling right after IHP triggers (let it heat)
- ❌ Don't expect perfection on first cycle (learning takes time)
- ❌ Don't ignore error messages (they tell you what's wrong)

---

## ⚠️ When to Check the Logs

Check Home Assistant logs if:

- ❌ Heating never triggers
- ❌ Heating triggers at random times
- ❌ IHP integration won't load
- ❌ Any error messages appear

**To check logs:**
1. Settings → System → Logs
2. Search for `intelligent_heating_pilot`
3. Enable debug mode to see more details

---

## 🔗 Related Documentation

- **[CHANGELOG](../CHANGELOG.md)** - What's new in this version?
- **[Architecture Guide](../ARCHITECTURE.md)** - For developers: How IHP is built
- **[CONTRIBUTING Guide](../CONTRIBUTING.md)** - How to contribute improvements

---

## 🤔 Frequently Asked Questions

### Q: How many heating cycles before IHP is accurate?

**A:** Typically 5-10 cycles. IHP uses conservative defaults initially and becomes more confident as it learns. After 20+ cycles, predictions are usually very accurate.

### Q: Can I use IHP with multiple thermostats?

**A:** Yes! Create multiple IHP instances (one per thermostat). Each learns independently.

### Q: What happens if I don't have outdoor temperature sensor?

**A:** That's fine! IHP works without it, just uses default assumptions. Adding the sensor improves accuracy.

### Q: Is IHP making my heating worse?

**A:** Unlikely. IHP only triggers your existing scheduler at calculated times. Your thermostat still controls the actual heating. If problems occur, disable IHP (uninstall integration) and check thermostat works normally.

### Q: Can I manually override IHP?

**A:** Yes. You can manually turn on/off your thermostat anytime. IHP won't interfere with manual control.

### Q: Where is IHP storing my data?

**A:** All learning data is stored locally on your Home Assistant instance. Nothing is sent to cloud or external services.

### Q: What happens when I go on vacation? Does IHP stop automatically?

**A:** Yes! IHP automatically stops when you disable your scheduler or when scheduler conditions aren't met. Here's how:

**When scheduler is disabled (state = "off"):**
- IHP detects no upcoming timeslots
- Anticipation sensors return to `unknown`
- No heating will be triggered
- No action needed from you

**When scheduler conditions aren't met (e.g., vacation mode):**
- IHP calls `run_action` with `skip_conditions: false`
- The scheduler respects its own conditions (like `input_boolean.vacation`)
- If conditions fail, heating won't trigger
- IHP stays ready but inactive

**How IHP interacts with your system:**
- IHP does NOT directly control VTherm
- IHP triggers the scheduler's `run_action` service
- The scheduler then controls VTherm based on its conditions
- This ensures all your existing automations and conditions work as expected

**For vacation mode:**
1. Set your thermostat to eco mode (optional)
2. Disable your scheduler (turn switch to "off")
3. IHP automatically becomes inactive
4. When you return, enable the scheduler
5. IHP resumes normal operation

Rest assured, you can go on vacation without any additional configuration!

---

## 📞 Getting Help

- 💬 **Questions?** Ask on [GitHub Discussions](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions)
- 🐛 **Found a bug?** Report on [GitHub Issues](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues)
- 📖 **Need more details?** Check [Troubleshooting Guide](TROUBLESHOOTING.md)

---

## 🎓 Next Steps

1. **👉 First time?** Start with [Installation](INSTALLATION.md)
2. **👉 Just installed?** Go to [Configuration](CONFIGURATION.md)
3. **👉 Want to understand it?** Read [How It Works](HOW_IT_WORKS.md)
4. **👉 Something wrong?** Check [Troubleshooting](TROUBLESHOOTING.md)

---

**Happy heating!** 🔥

_Intelligent Heating Pilot v0.3.0 - Documentation Last Updated: December 2025_
