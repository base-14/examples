class OrdersController < ApplicationController
  def index
    @orders = current_user.orders.includes(food: :hotel).order(created_at: :desc)
  end
  
  def new
    @food = Food.find(params[:food_id])
    @order = Order.new
  end
  
  def create
    @food = Food.find(params[:food_id])
    @order = current_user.orders.build(order_params)
    @order.food = @food
    
    if @order.save
      redirect_to orders_path, notice: 'Order placed successfully!'
    else
      render :new, status: :unprocessable_entity
    end
  end
  
  def show
    @order = current_user.orders.find(params[:id])
  end
  
  private
  
  def order_params
    params.require(:order).permit(:quantity)
  end
end
