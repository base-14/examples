class HomeController < ApplicationController
  def index
    @hotels = Hotel.all
  end
end
