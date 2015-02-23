require("storm") -- libraries for interfacing with the board and kernel
require("cord") -- scheduler / fiber library

----------------------------------------------
-- RELAY class
--   basic RELAY functions associated with a shield pin
--   assume cord.enter_loop() is active, as per stormsh
----------------------------------------------
local RELAY = {}

function RELAY:new(relaypin)
   assert(relaypin and storm.io[relaypin], "invalid pin spec")
   obj = {pin = relaypin}		-- initialize the new object
   setmetatable(obj, self)	-- associate class methods
   self.__index = self
   storm.io.set_mode(storm.io.OUTPUT, storm.io[relaypin])
   return obj
end

function RELAY:pin()
   return self.pin
end

function RELAY:on()
   storm.io.set(1,storm.io[self.pin])
end

function RELAY:off()
   storm.io.set(0,storm.io[self.pin])
end

return RELAY

