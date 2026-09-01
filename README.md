# genmon
# Generator Monitoring Application using a Raspberry Pi and WiFi

This project will monitor a backup generator that utilizes the Generac Controllers over a WiFi or wired connection.  The following generator controllers are supported:

* Generac [Nexus](https://raw.githubusercontent.com/jgyates/genmon/master/Diagrams/Nexus_Controller.jpg) and [Evolution](https://raw.githubusercontent.com/jgyates/genmon/master/Diagrams/Evolution_Controller.jpg) (1.0 and 2.0) Controller (Used in Generac's residential product line)
* Honeywell and Eaton use the Generac Controllers, they call them Sync 1.0 (Nexus), Sync 2.0 (Evolution 1.0) and Sync 3.0 (Evolution 2.0)
* Generac [H-100](https://github.com/jgyates/genmon/wiki/Appendix-G-Generac-H-100,-G-Panel-and-PowerZone-Controllers) Industrial Controllers
* The H-100 controller is used in industrial generators from Generac and Eaton.
* Generac G-Panel based Industrial Controllers
* Generac [PowerPact](https://github.com/jgyates/genmon/wiki/Appendix-R---Replacing-Generac-MobileLink-with-Genmon-on-a-PowerPact-7.5-KW)
* [2008 Era Generac Pre-Nexus](https://raw.githubusercontent.com/jgyates/genmon/master/Diagrams/2008-PreNexusController.jpg) controllers. See [this](https://github.com/jgyates/genmon/wiki/Appendix-D-Known-Issues) page for more info.
* Generac [PowerZone Pro/Sync and PowerZone 410](https://github.com/jgyates/genmon/wiki/Appendix-G-Generac-H-100,-G-Panel-and-PowerZone-Controllers) controllers
* Custom Controller Interface for supporting other generators that use modbus over serial or modbus over TCP. More info on this is located [here](https://github.com/jgyates/genmon/wiki/Appendix-N-Genmon-Supporting-Other-Controller-Types). Deep See Electronics, Briggs & Stratton, etc.
* [Deep See Electronics 7320MKII Controller](https://github.com/jgyates/genmon/wiki/Appendix-N-Genmon-Supporting-Other-Controller-Types)
* [ComAp Controller](https://github.com/jgyates/genmon/wiki/Appendix-N-Genmon-Supporting-Other-Controller-Types)
* [Briggs & Stratton GC-1031/GC-1032](https://github.com/jgyates/genmon/wiki/Appendix-P-Briggs-and-Stratton-Controller-Information)
* [Kohler APM604](https://powersystems.kohlerenergy.com/en/product/apm603)
* [MEBAY DC4x - DC9x controllers](https://mebay.cn/#/index/product_display/list?sign=product_display&id=39&level=1&random=10)
* [SmartGenSmartGen HGM40x0](https://github.com/jgyates/genmon/wiki/Appendix-N-Genmon-Supporting-Other-Controller-Types)

The project is written mostly in python and has been tested with a Raspberry Pi 3 (Pi Zero, Pi Zero W, Pi Zero 2W, Pi 2, Pi 3b+ and Pi 4 have also been validated). 32 and 64 bit version of raspbian have been used with the project. To use this project you would need to create a physical enclosure for your raspberry pi and possibly [make a cable](https://github.com/jgyates/genmon/wiki/3.1--Making-a-Cable) to connect the raspberry pi to the generator controller or purchase [pre-assembled hardware](https://github.com/jgyates/genmon/wiki/2--Hardware#custom-hat). If you are comfortable doing these things and you have a backup generator that has a supported controller, then this project may be of interest to you.

## Functionality
The software supports the following features:

* Monitoring of the generator to detect and report the following:
    * Maintenance, Start / Stop and Alarm Logs (No Maintenance log exist on Nexus or Industrial Gens)
    * Display Generator Serial Number
    * Generator warnings and faults
    * Generator Status:
        * Engine State
            - Generator Switch State (Auto, On, Off)
            - Generator Engine State (Stopped, Starting, Exercising, Running Manual, Running Utility Loss, Stopped due to Alarm, Cooling Down)
            - Battery Voltage and Charging Status
            - Relay Output State: (Starter, Fuel Relay, Battery Charger, others for liquid cooled models)
            - Engine RPM, Hz and Voltage Output
            - Generator Controller Time
        * Line State
            - Utility Voltage Level
            - Transfer Switch State (Evolution liquid cooled model and Industrial Gens with HTS/MTS/STS Transfer Switches models only)
        * Outage Information
            - Time since last outage
            - Current Utility Voltage
            - Min and Max Utility Voltage since program started
        * Maintenance Information
            - Weekly Exercise time, day (biweekly and monthly if supported by your generator)
            - Hours till next scheduled service
            - Total Run Hours
            - Firmware and Hardware versions
        * Various statistics from the generator monitor including time since program launched,
              MODBUS / serial communications health and program health.
* Native PWA Web Push Notifications (with RFC 8292 VAPID encryption and Apple APNs / Safari PWA support for iOS, macOS, Android, Windows)
* Wi-Fi Band Indicator (2.4 GHz, 5 GHz, 6 GHz) on dashboard signal tile and platform diagnostics
* Script Logs Viewer (`/#/logs`) with live error highlighting, acknowledgment, and direct dashboard tile click navigation
* Manual Backups Console with live streaming terminal output for Daily Archives and Weekly SD Card Image routines
* Enhanced Session Security with global "Logout All Devices" session revocation, Passkey / WebAuthn, and MFA backup codes
* Email notification of Engine state, Switch state, and Alarm conditions
* Web based application for viewing status of the generator
* Limited and Full Rights login for web interface
* SMS notifications of Generator state and power outages (via Twilio SMS API or Expansion Cellular Modem)
* Push notifications (via pushover.net, slack)
* CallMeBot notifications for whatsapp and telegram
* syslog logging of generator events
* Command Line application (all the functionality of email).
* Ability to set exercise time and generator time remotely
* Remote start, stop, exercise, and transfer switch activation
* Power, Current output and fuel consumption on selected models
* MQTT integration for third party home automation support
* Service Journal for logging maintenance, repair, etc.
* Comprehensive Unit and Integration Test Suite (`python3 -m unittest discover -s tests -p "test_*.py"`)

![Generator Monitor Web Interface](https://raw.githubusercontent.com/jgyates/genmon/master/Diagrams/Web_UI_Status.png)

## Support
This project is free to use under the posted license agreement. It was written and is supported by one person with testing and some documentation supported by users of the software. I originally created this project for my personal use however I decided to make the project available to anyone interested, however I do accept tips via paypal:

[![paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif)](https://www.paypal.com/cgi-bin/webscr?cmd=_donations&business=8Z4TSR22RLMWQ&lc=US&item_name=jgyates&item_number=jgyates&currency_code=USD&bn=PP%2dDonationsBF%3abtn_donate_LG%2egif%3aNonHosted)

## System Requirements
- Genmon 2.0 and higher requires Python 3.9 or higher.
- A linux based operating system (mostly for file system storage location)
- A TCP/IP network connection (either wired or wireless) for communicating generator status

## Hardware Available for Purchase
While you have the option of purchasing all of the components individually, there is an option for purchasing custom designed hardware that will simplify the hardware assembly process. More info is available [here](https://github.com/jgyates/genmon/wiki/2--Hardware#custom-hat).

## Testing
The repository includes a comprehensive automated test framework covering unit and integration tests:
```bash
python3 -m unittest discover -s tests -p "test_*.py"
```
Continuous integration is managed via GitHub Actions across Python 3.9–3.12.

## Placement of your Raspberry Pi
If you have a large generator, the placement of your Raspberry Pi could be important due to [EMI](https://en.wikipedia.org/wiki/Electromagnetic_interference). Larger generators can produce more EMI when starting. If you see CRC errors, check the validity of your cable or move the Raspberry Pi enclosure further away from the engine block.

## Connectivity
This application was written to be agnostic of the underlying network media (i.e. WiFi, Ethernet, etc). Testing and development was performed with WiFi with access points connected to an uninterruptible power supply (UPS) so connectivity is not lost when power is transferred from utility to the generator.

For automated network recovery and auto-reboot resilience during router/AP disconnects, see `net_watchdog.sh` and [Section 10 of the Deployment Guide](DEPLOYMENT_GUIDE.md#10-network-watchdog--auto-reboot-net_watchdogsh).

## Controller Selection
Genmon supports several types of generator controllers. The following table shows each controller supported and how to configure genmon to support each controller.

| Controller | Description | Setup |
|---|---|---|
| Evolution 1.0 / 2.0 Air Cooled, Evolution Liquid Cooled, Nexus Air Cooled, Nexus Liquid Cooled, Generac PowerPact | Generac Residential | Default setting: Settings -> Advanced -> Controller Type -> evolution_nexus |
| [Generac H-100 and G-Panel](https://github.com/jgyates/genmon/wiki/Appendix-G-Generac-H-100,-G-Panel-and-PowerZone-Controllers) | Industrial Generac | Settings -> Advanced -> Controller Type -> h_100 |
| [Generac Power Zone Pro](https://github.com/jgyates/genmon/wiki/Appendix-G-Generac-H-100,-G-Panel-and-PowerZone-Controllers) | Industrial Generac | Settings -> Advanced -> Controller Type -> powerzone_pro |
| [Generac Power Zone 410](https://github.com/jgyates/genmon/wiki/Appendix-G-Generac-H-100,-G-Panel-and-PowerZone-Controllers) | Industrial Generac | Custom Controller Config -> Power_Zone_410.json |
| [Briggs & Stratton GC-1032](https://github.com/jgyates/genmon/wiki/Appendix-P-Briggs-and-Stratton-Controller-Information) | Residential | Custom Controller Config -> Briggs_Stratton_GC-1032.json |
| ComAP Controller | [ComAP IG-NT](https://www.comap-control.com/products/controllers/paralleling-gen-set-controllers/inteligen/inteligen-nt/) | Custom Controller Config -> ComAP.json |
| Deepsea | [Deepsea](https://www.deepseaelectronics.com/genset) | Custom Controller Config -> Deepsea_controller.json |
| Kohler APM603 | [Product Page](https://powersystems.kohlerenergy.com/en/product/apm603) | Custom Controller Config -> Kohler_APM603.json |
| [MEBAY DCxx (DC04-DC90)](https://github.com/jgyates/genmon/wiki/Appendix-R---MEBAY-Controller-with-RS-485) | [MEBAY Controllers](https://mebay.cn/#/index/product_display/list?sign=product_display&id=39&level=1&random=7) | Custom Controller Config -> MEBAY_DCxx.json |
| SmartGen HGM40x0 | [SmartGen Series](https://www.smartgen-america.com/catalog/products/genset-controllers/) | Custom Controller Config -> SmartGen_HGM4000.json |
| [Basler DGC 2020HD](https://github.com/jgyates/genmon/wiki/Appendix-U-Basler-DGC-2020HD-Controller) | [Product Page](https://www.basler.com/product/dgc-2020hd-digital-genset-controller/) | Custom Controller Config -> Basler_DGC_2020HD.json |

# Documentation
* [Genmon Project Wiki](https://github.com/jgyates/genmon/wiki)
* [Complete Setup, Backup & Deployment Guide](DEPLOYMENT_GUIDE.md)
* [Network Watchdog Documentation](README_net_watchdog.md)
* [Service Journal Sync Addon Documentation](addon/README_genmaint_sync.md)

### SDLC Documentation
| Document | Description |
|---|---|
| [Implementation Plan](docs/IMPLEMENTATION_PLAN.md) | Technical architecture & design plan |
| [Task List](docs/TASK_LIST.md) | Active work items & delivery status |
| [Walkthrough](docs/WALKTHROUGH.md) | Verification and completion summary |

