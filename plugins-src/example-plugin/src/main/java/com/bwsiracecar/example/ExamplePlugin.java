package com.bwsiracecar.example;

import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.plugin.java.JavaPlugin;

/** Template plugin. Copy this directory, rename it, and start building. */
public class ExamplePlugin extends JavaPlugin {

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!command.getName().equalsIgnoreCase("hello")) {
            return false;
        }
        sender.sendMessage("Hello from BWSI Racecar!");
        return true;
    }
}
