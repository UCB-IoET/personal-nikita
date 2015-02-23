require("storm") -- libraries for interfacing with the board and kernel
require("cord") -- scheduler / fiber library
Relay = require("relay")
Temp = require("temp")
----------------------------------------------
-- Toaster  class
--   basic TOASTER functions associated with a shield pin
--   assume cord.enter_loop() is active, as per stormsh
----------------------------------------------
local TOASTER = {}

function TOASTER:new(relaypin)
   assert(relaypin and storm.io[relaypin], "invalid pin spec")
   r = Relay:new(relaypin)
   t = Temp:new()
   obj = {relay = r, targetTemp = 0, state = false, tempSensor = t}
   setmetatable(obj, self)	-- associate class methods
   self.__index = self
   return obj
end
function TOASTER:init()
   storm.os.invokePeriodically(5*storm.os.SECOND, function()
	   if self.state == true then
	       print("Toaster is on!")
	       currentTemp = self:getTemp()
	       if currentTemp > self.targetTemp then
		   self.relay:off()
		   print("BUT it's too HOT now: ", currentTemp , self.targetTemp)
	       else
		   self.relay:on()
		   print("BUT it's too COLD now: ", currentTemp, self.targetTemp)
	       end
	   else
	       self.relay:off()
	       print("Toaster is off!")
	   end
   end)
end
function TOASTER:on()
   self.state = true
   self.relay:on()
end

function TOASTER:off()
   self.state = false
   self.relay:off()
end

function TOASTER:getTemp()
   return self.tempSensor:getTemp() 
end

function TOASTER:setTemp(target)
   self.targetTemp = target
end

return TOASTER

