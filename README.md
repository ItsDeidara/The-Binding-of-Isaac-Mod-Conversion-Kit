# The-Binding-of-Isaac-Mod-Conversion-Kit

This is a utilitly to convert mods the PC version of The Binding of Isaac to their console counterparts.

You need to have a modified console in order to use the converted mods. I have personally tested this with the Wii U, Playstation Vita, and Nintendo 3DS


# UPDATE: 7/10/17
With some friendly information from SciresM The Binding of Isaac on the Nintendo Switch uses the same file formats and structure as the other consoles. So this tool should still work just the same there. Provided you can access the game's files

# UPDATE: 11/20/18
Here are some notes I took when making some example mods for the Nintendo Switch to help you when you try and convert your own mods. There of course may be simple fixes to these, however the converter works well enough for now imo If anyone would like to program a solution to these "bugs" I will accept the pull request

```
pocketitems.xml can not be used from mods. This crashes the game instantly. This may be able to be converted but I have not seen a mod affected negativly by leaving this out

Room xml files  can't include "_converted" within them or else the game will crash

You can't add additional rooms to the game. For example Godmode adds an "enemy_compounds" folder to the rooms directory. this can not be used even with the fixed XML naming or else the game will crash.
```
