class ItemsController < ApplicationController
  def create
    permitted = item_params
    tracer = OpenTelemetry.tracer_provider.tracer("items-controller")
    item = nil

    tracer.in_span("item.create", attributes: { "item.title" => permitted[:title] }) do |span|
      if Item.exists?(title: permitted[:title])
        trace_id = span.context.hex_trace_id
        span_id = span.context.hex_span_id
        Rails.logger.warn "[trace_id=#{trace_id} span_id=#{span_id}] Duplicate title detected, creating anyway: #{permitted[:title]}"
      end

      item = Item.create!(permitted)
      span.set_attribute("item.id", item.id)
    end

    render json: item_json(item), status: :created
  end

  def show
    item = Item.find(params[:id])
    render json: item_json(item)
  end

  private

  def item_params
    params.require(:item).permit(:title, :description)
  end

  def item_json(item)
    {
      id: item.id,
      title: item.title,
      description: item.description,
      created_at: item.created_at,
      updated_at: item.updated_at
    }
  end
end
